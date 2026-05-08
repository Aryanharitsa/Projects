# 🚦 WaySafe — Smart Tourism Safety Intelligence

WaySafe is a **safety-first navigation & incident-response system** for tourists.
It scores any location 0–100, plans risk-aware routes (with a temporal-forecast
mode), and now ships a **Live Trip Companion** that walks the user through the
journey itself — proactive geofence + risk-corridor alerts, a trusted-contacts
broadcast loop, and an auto-SOS rule when a traveller stalls in dangerous
territory.

Built on Streamlit + pure-Python physics (no external maps API, no XGBoost,
no LLM dependency). Runs on a laptop, ships in a single `streamlit run`.

---

## ✨ Headline features

- **Live safety score (0–100)** — composite penalty across geofences,
  recency- & severity-weighted nearby incidents, late-night windows and
  help-POI density. Bands: Safe / Caution / High Risk / Danger.
- **Risk-aware route planner** — pure-Python A\* over a snapped lat/lon
  grid, edge cost `haversine_km · (1 + α · risk(midpoint))`. Runs *fastest*
  (α=0) and *safest* (α=4.5) in parallel; results compare in dual cards
  with mini score rings, GPX downloads and Google-Maps deeplinks.
- **Hazard forecast (empirical-Bayes)** — historical incidents binned by
  `½-km cell × DOW × hour`, kernel-smoothed across the 3×3 time
  neighbourhood, shrunk toward a per-bucket city prior, Poisson-saturated
  to a 0–100 risk. Ships a 24-h curve, expected-category mix, hotspot
  ranking and a *find best departure* sweep (±2 h at 30-min steps).
- **Forecast-aware safest route** — each edge is priced by the *predicted*
  risk at the time the traveller will reach its midpoint
  (`t = depart + cum_km / 32 km/h`), blended 65/35 with current-time risk.
- **🆕 Live Trip Companion** — turns a planned route into a live journey
  with proactive alerts and trusted-contact broadcasts. Details below.
- **Authority dashboard** — operational map, category & time-series
  breakdowns, pending-incident queue with verify + broadcast workflow,
  next-24h forecast curve and likely-hotspots panel.
- **Tamper-evident audit** — Merkle-rollup auditor over incident hashes
  (no blockchain required, anchor on-chain later if needed).

---

## 🧭 Live Trip Companion (round-3 closer)

The previous rounds gave the user a static *plan*. Round 3 closer makes
WaySafe **travel with the user**.

### What fires, and when

| Alert kind        | Severity     | Trigger                                                           |
|-------------------|--------------|-------------------------------------------------------------------|
| `departure`       | info         | trip starts                                                       |
| `risk_ahead`      | warn / critical | look-ahead scan finds a sample with `risk ≥ 0.45` in the next 1.5 km |
| `geofence_enter`  | warn         | current position crosses *into* a geofenced risk polygon          |
| `geofence_exit`   | info         | current position crosses *out of* a geofenced risk polygon        |
| `safer_segment`   | info         | risk ahead drops below `0.32` after a recent `risk_ahead`         |
| `auto_sos`        | critical     | no progress for `≥5 min` while inside a high-risk zone (or a manual press) |
| `arrival`         | info         | `km_travelled ≥ distance_km`                                      |

Every fired alert is deduped on `(kind, ~110 m bucket)` within a 90 s
cooldown so the same risk corridor doesn't spam the feed. Each alert can
fan out to opted-in trusted contacts; the simulated SMS body is composed
deterministically per `(alert.kind, contact.name)` and a `maps.google.com`
deeplink to the live position is included for SOS / risk dispatches.

### Position simulation

A `RouteResult` is snapshotted into a `TripPlan` with a coord prefix-sum.
Every Streamlit re-run calls `companion.tick(trip, …)` which advances
`km_travelled` by `(wall_dt · AVG_TRAVEL_KMH · speed_factor)`, interpolates
the current `(lat, lon)` along the prefix-sum, samples `point_risk` on the
next 1.5 km of path at 12 evenly-spaced offsets, evaluates geofence
membership, and emits new alerts. A real GPS feed slots into the same
`tick()` call by setting `speed_factor=1.0` and back-feeding actual
positions.

### UI

- **Live header** — conic-gradient progress ring, ETA / distance-left /
  start-time / arrival tiles, and a pulsing live-status pill.
- **Map** — planned route + trail of past heartbeats (cyan polyline) +
  current pulsing position dot with a glow halo + origin/destination
  pinpoints + the existing incident heatmap.
- **Alerts feed** — 8 most-recent alerts, severity-tinted left-border
  ribbon (info teal / warn amber / critical rose), relative timestamps.
- **Look-ahead panel** — risk at `+0.4 km / +0.9 km / +1.5 km` slices,
  hue-graded bars, dominant hazard category labelled where known.
- **Trusted-contacts strip** — chip per contact with a hash-coloured
  gradient avatar + opt-in count; `Manage contacts` expands a CSV-style
  data editor with one-click save.
- **Simulated dispatches log** — every broadcast appended live, kind-pill
  badges (`departure` teal · `arrival` mint · `auto_sos` rose).
- **Controls** — Pause / Resume / Cancel · live speed select-slider
  (1× / 2× / 4× / 8× / 16×) · `🆘 Manual SOS` · `Auto-advance` toggle that
  reruns the page every 2 s for a true *live* feel.
- **Trip Log tab** — a digest row per completed/cancelled trip (origin →
  dest, route mode, km travelled, alert breakdown chips, SOS pill if any,
  status-coloured % complete) plus JSON export and the existing PDF
  report.

---

## 🏗 Layout

```
WaySafe/
│── app.py              # Streamlit shell — Tourist / Authority / Auditor roles, 8 tabs
│── safety.py           # Live 0–100 score + heatmap weights + point_risk()
│── routing.py          # A* over priced grid + GPX + forecast-aware variant
│── forecast.py         # Empirical-Bayes spatiotemporal hazard model
│── companion.py        # 🆕 Live Trip Companion — trips, alerts, broadcasts
│── theme.py            # Dark theme + render_* helpers
│── utils.py            # haversine, point_in_polygon, sha256, build_merkle
│── data/
│   │── incidents.csv          # seeded reports with cluster patterns
│   │── poi.csv                # hospitals / police / clinics / fire
│   │── goa_geofences.geojson  # named risk polygons
│   │── broadcasts.csv         # active authority broadcasts
│   │── sos.csv                # legacy SOS log
│   │── contacts.csv           # 🆕 trusted contacts (live editable)
│   │── notifications.csv      # 🆕 simulated SMS dispatch log (auto-grown)
│   └── uploads/               # photo evidence
│── requirements.txt
└── README.md
```

---

## ⚙️ Quick start

```bash
git clone https://github.com/Aryanharitsa/Projects.git
cd Projects/WaySafe

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
```

### Headline demo — Aguada → Baga at Sat 22:00

1. Sidebar → set lat/lon to **15.4925, 73.7825** (Aguada cliffs).
2. **Plan Route** tab → destination *Baga* (or custom 15.55, 73.77), depart
   at **Sat 22:00**, *Use temporal forecast* on, **Plan routes**.
3. **Live Trip** tab → pick `safest` (or `forecast-safest`), choose
   `4×` simulation, **▶ Start journey**.
4. Watch:
   - departure broadcasts dispatch to the seeded contacts (Aryan, Mom, Roomie),
   - the position dot crawls through the Aguada cliff geofence —
     `geofence_enter` fires with the zone name,
   - the look-ahead panel spikes amber/rose on the Baga incident cluster
     and `risk_ahead` lands with the dominant category (`accident`) named,
   - flip *Auto-advance* on to watch alerts stream in real time,
   - `Manual SOS` (or stalling for 5 min in the geofence) triggers
     `auto_sos` + a SOS broadcast row to every contact opted into
     `auto_sos`.

---

## 📐 Math reference

**Live safety score**
```
penalty = 25·1[geofence] + Σ_recent sev·rec·dist·verified·1.6
        + 8·1[late_night] − min(3·n_help_POIs, 9)
score   = clip(100 − penalty, 0, 100)
```

**Route edge cost**
```
cost(u, v) = haversine_km(u, v) · (1 + α · risk(midpoint))
   α = 0   →  fastest         α = 4.5  →  safest
```

**Hazard forecast (empirical-Bayes)**
```
λ̂(c, t) = (Σ_{c′,t′ ∈ N(c,t)} k_{c′,t′} · K(c,t; c′,t′) + α · π_t) /
          (kernel_mass + α)
risk(c, t) = 1 − exp(−κ · λ̂(c, t)),    κ=0.85, α=3.0
```

**Live Trip auto-SOS rule**
```
fire_auto_sos ⇔ stall_min ≥ 5  ∧  in_red_zone
   in_red_zone ⇔ here_risk ≥ 0.45
                ∨ peak_risk_in_next_1.5km ≥ 0.45
                ∨ inside any geofence polygon
```

---

## 📍 Roadmap

- [x] Real safety intelligence engine + heatmap + dark UI (round 1)
- [x] Risk-aware A\* router + dual-route UI (round 2)
- [x] AI-powered hazard forecasting (round 3 opener)
- [x] **Live Trip Companion + trusted-contacts broadcast** (round 3 closer)
- [ ] Multi-stop itinerary chaining (visit A → B → C; depart-at optimised)
- [ ] Real-time push (web-sockets) instead of file-tail simulation
- [ ] Mobile-first PWA shell with native geolocation feed
- [ ] Live traffic / road-closure overlay (HERE or Mapbox)

---

## 👨‍💻 Author

Built with ❤️ by **Aryan D Haritsa** — Student @ PES University · Entrepreneur ·
AI · Full-stack · research.
