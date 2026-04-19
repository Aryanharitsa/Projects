# 🚦 WaySafe — Smart Tourism Safety

A Streamlit app that turns crowd-reported incidents, geofenced risk zones, and
help-POI density into a **live, explainable safety score** for any lat/lon — with
a tamper-evident Merkle audit trail on top.

> Not another dashboard. WaySafe actually *scores* where you are, tells you
> *why* it scored that way, and draws a real incident heatmap — all from pure
> Python, no third-party maps-API key required.

---

## ✨ What's inside

| | |
|---|---|
| 🧮 **Safety Intelligence engine** (`safety.py`) | Composite 0–100 score: geofence hit ↓, severity- & recency-weighted incidents within 3 km ↓, late-night window ↓, help POIs within 2 km ↑. Every deduction is returned as a human-readable factor. |
| 🔥 **Incident risk heatmap** | `pydeck` HeatmapLayer weighted by category severity × recency (72 h half-life) × verified-bump (×1.4). |
| 📱 **Tourist app** | Live score ring, hazard report (photo → SHA-256 fingerprint), nearby broadcast alerts, one-tap SOS, trip-report PDF. |
| 🛰 **Authority dashboard** | Verified/pending/SOS KPIs, category breakdown, incidents-over-time, verify-and-broadcast workflow. |
| 🔐 **Merkle rollup auditor** | Hash every incident, build a Merkle root, and produce per-leaf proofs. Tamper-evident without a blockchain. |
| 🌙 **Offline-first** | Flip "Offline mode" — reports queue in an in-memory outbox and flush on `Sync`. |
| 🎨 **Dark gradient theme** | Custom CSS, ring gauge, status pills — no default-Streamlit look. |

---

## 🧠 How the score is computed

```text
score = clamp(0, 100 − Σ penalties + Σ bonuses)
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

## 🚀 Run it

```bash
git clone https://github.com/Aryanharitsa/Projects.git
cd Projects/WaySafe
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the app, pick a view in the sidebar, and nudge your location to see the
score update in real time. Try:

- `15.55, 73.76` — inside the Baga–Calangute belt (Caution zone)
- `15.49, 73.78` — Aguada coastline
- flip **Offline mode**, file a hazard, then **Sync**

---

## 📂 Layout

```
WaySafe/
├── app.py               # Streamlit UI — views, tabs, forms
├── safety.py            # Score engine + heatmap weights
├── theme.py             # Dark theme CSS + ring/brand components
├── utils.py             # haversine, point-in-polygon, SHA-256, Merkle
├── data/
│   ├── goa_geofences.geojson
│   ├── incidents.csv    # hazard reports
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
from safety import compute_safety
geo = json.load(open("data/goa_geofences.geojson"))
inc = list(csv.DictReader(open("data/incidents.csv")))
poi = list(csv.DictReader(open("data/poi.csv")))
r = compute_safety(15.55, 73.76, inc, geo, poi, now=datetime(2025,1,15,14,0))
print(r.score, r.band)
for f in r.factors: print(" ", f)
PY
```

---

## 🛣 Roadmap

- [ ] Safety-weighted routing (OSRM / OpenRouteService) using the score as an edge penalty
- [ ] Live-traffic overlay & incident prediction (XGBoost on reported hazard history)
- [ ] Push-notification channel for broadcasts (Web Push / FCM)
- [ ] PostgreSQL + PostGIS backend to replace CSVs once scale demands it
- [ ] Anchor daily Merkle roots on-chain for immutable provenance

---

## 👨‍💻 Author

Aryan D Haritsa — PES University · AI, Full-Stack & Research Enthusiast
