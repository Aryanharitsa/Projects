# 🚦 WaySafe — Smart Tourism Safety Intelligence

WaySafe is a **safety-first navigation & incident-response system** for tourists.
It scores any location 0–100, plans risk-aware routes (with a temporal-forecast
mode), threads multiple stops into a single safety-aware day with the
**Multi-Stop Itinerary Planner**, and ships a **Live Trip Companion** that
walks the user through the journey itself — proactive geofence + risk-corridor
alerts, a trusted-contacts broadcast loop, and an auto-SOS rule when a
traveller stalls in dangerous territory. The new **Sentinel** mode goes one
level higher: it clusters raw incidents into discrete hotspots and grades each
by **velocity** (recent rate vs its own historical baseline) so the tourist
sees what's *escalating right now*, not just where activity has accumulated.

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
- **🆕 Sentinel — Live Cluster Intel** — DBSCAN over haversine groups raw
  incidents into discrete hotspots; each cluster is graded
  Critical / Emerging / Steady / Cooling by **velocity** (recent rate ÷
  historical baseline rate). A global **Risk Pulse** rolls every cluster up
  into one Calm/Watch/Active/Critical state with an always-on **Watch
  banner** on the Map tab. Per-cluster cards show velocity vs the 1.0×
  baseline, a 4-cell stat grid (recent · prior · severity · verified %),
  a category mix bar, a 30-day activity sparkline, and a recommended
  action tailored to the user's distance from the hotspot edge.
- **Multi-Stop Itinerary Planner** — chain N stops into one
  safety-aware day. Order is solved with a 2-opt over the haversine
  distance matrix, every leg is priced by the same risk-aware A*, the
  schedule rolls up into a **Gantt timeline** and the whole plan exports
  to **iCal** (.ics) so it drops straight into Apple/Google/Outlook
  calendars with `geo:` deeplinks at every waypoint. A `±2 h` start-window
  sweep re-plans the entire itinerary at 9 candidate departures and
  surfaces the safest one.
- **Live Trip Companion** — turns a planned route into a live journey
  with proactive alerts and trusted-contact broadcasts. Details below.
- **Authority dashboard** — operational map, category & time-series
  breakdowns, pending-incident queue with verify + broadcast workflow,
  next-24h forecast curve and likely-hotspots panel.
- **Tamper-evident audit** — Merkle-rollup auditor over incident hashes
  (no blockchain required, anchor on-chain later if needed).

---

## 🛰️ Sentinel — Live Cluster Intel (Day 26)

Where the heatmap tells you *where* incidents are dense, Sentinel tells you
*what's escalating right now*. It's a fresh tab between **Forecast** and
**Report Hazard**, plus a persistent **Watch banner** on the Map tab that
surfaces emerging hotspots everywhere in the app.

### Pipeline

| Step | Algorithm | Notes |
|---|---|---|
| 1. cluster | pure-stdlib **DBSCAN** over haversine distance | ε km radius + min-samples; -1 = noise |
| 2. summarize | severity × recency weighted centroid + bounding radius | per-cluster category mix, severity mean, verified % |
| 3. velocity | `(recent_rate + ε) / (baseline_rate + ε)` with ε=0.005 | numerator: recent window (default 30 d); denominator: prior baseline window (default 60 d) |
| 4. classify | velocity → status | Critical ≥ 2.5×, Emerging ≥ 1.3×, Steady 0.6–1.3×, Cooling < 0.6× |
| 5. roll-up | global **Risk Pulse** | Critical / Active / Watch / Calm based on cluster mix |

A previously-dormant cluster that fires several recent incidents reads as
high velocity — exactly what you want for emergent-pattern detection. The
small ε floor on the baseline rate avoids division blow-ups for brand-new
clusters while still pushing them firmly into the Critical band.

### Velocity grades

```
velocity ≥ 2.5    →  Critical   (now > 2.5× historical pace)
velocity ≥ 1.3    →  Emerging   (heating up)
0.6 ≤ vel < 1.3   →  Steady     (active at baseline)
velocity < 0.6    →  Cooling    (slowing down)
recent_count = 0  →  Cooling    (no live signal regardless of ratio)
```

### Global Risk Pulse

```
n_critical ≥ 1                       →  Critical
n_emerging ≥ 2                       →  Active
n_emerging ≥ 1  or  n_steady ≥ 3     →  Watch
otherwise                            →  Calm
```

### UI

- **Risk-Pulse hero** — band-coloured status block with animated ring,
  one-line headline, 4 stat tiles (clusters · last-window count · prior-window
  count · velocity) and a chip strip breaking out Critical / Emerging /
  Steady / Cooling counts plus the dominant category.
- **Sentinel parameters** — collapsible expander with 4 number inputs
  (`ε km`, `min_samples`, `recent_days`, `baseline_days`) that drive a
  live re-cluster on change.
- **Cluster map** — `PolygonLayer` halos coloured by status, white centre
  markers sized by recent count, faint incident dots underneath.
- **Per-cluster cards** — status pill, centroid + radius + last-seen + peak
  hour subtitle, **velocity bar** with a `1.0×` baseline tick at 25% so the
  user reads "how far above baseline" visually, 4-cell stat grid, category
  mix tag bar, **30-day activity sparkline**, and a recommended action that
  changes wording when the user is *inside* vs *near* vs *far from* a hotspot.
- **Watch banner** — always-on top-strip on the Map tab that fires whenever
  the pulse is anything other than Calm.

### What it adds over the existing heatmap

- The heatmap shows a fixed density snapshot. Sentinel **partitions** that
  density into discrete events and **scores each by direction of travel**.
- The forecast shows expected risk by time-of-day. Sentinel shows actual
  emerging patterns **in the last window** vs the recent past.
- The safety score is a point estimate. Sentinel gives the user a one-glance
  global state plus actionable per-cluster intel.

---

## 🗺️ Multi-Stop Itinerary Planner (Day 21)

A tourist day rarely has one destination. The Itinerary tab solves the
*open-path* travelling-salesman variant — start node fixed (the user),
remaining stops re-ordered, no return-to-origin — and chains the result
into one priced schedule.

### Solver

| Step | Algorithm | Cost minimised |
|---|---|---|
| 1. seed order | greedy nearest-neighbour from the fixed start | Σ haversine_km |
| 2. refine | open-path **2-opt** (≤ 12 stops), reverses any sub-tour including the tail | Σ haversine_km |
| 3. price legs | same `plan_safest / plan_fastest / plan_forecast_route` used for single-route mode | risk-aware A* edge cost |

The depart-time of leg *k* is `arrive_at(k-1) + dwell_min(stop_k-1)` so
the *forecast-safest* variant correctly times each midpoint along the
chain.

### Composite itinerary score

```
score = clip(  Σ(km_i · avg_safety_i) / Σ km_i  −  6 · #(legs with min_safety < 35),  0, 100)
```

### Exports

- **GPX** — a single file with one `<trk>` per leg and a `<wpt>` per
  stop (works with every map app).
- **iCal `.ics`** — one `VEVENT` per **leg** (TRAVEL category) and one
  per **dwell** (DWELL category). Floating local times, `GEO:` line on
  every event so calendar UIs deep-link to a map pin. Long
  `DESCRIPTION` lines are CRLF-folded per RFC-5545.
- **Maps deeplink** — every leg's coords concatenated and down-sampled
  to ≤ 9 waypoints, opens the full day in Google Maps.

### UI

- **Hero card** — composite score ring, mode pill, total km / travel
  time / dwell, breakdown of how many legs fall in each safety band
  (Safe / Mostly Safe / Caution / High Risk / Danger).
- **Gantt timeline** — solid travel bars coloured by per-leg safety,
  hatched teal dwell bars between them, a ruler with `%H:%M` ticks
  auto-stepped (10/30/60/120 min) to the day's span.
- **Per-leg cards** — distance, ETA, avg safety, min safety, risky-km,
  safety band pill, planner notes.
- **Combined map** — every leg drawn in a distinct accent over the
  incident heatmap & geofence polygons; stops labelled `N. Name`.
- **Best start-window sweep** — re-plans the full itinerary at ±2 h
  around the chosen depart, ranked by composite score.

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
│── app.py              # Streamlit shell — Tourist / Authority / Auditor roles, 10 tabs
│── safety.py           # Live 0–100 score + heatmap weights + point_risk()
│── routing.py          # A* over priced grid + GPX + forecast-aware variant
│── forecast.py         # Empirical-Bayes spatiotemporal hazard model
│── itinerary.py        # Multi-stop planner — 2-opt order + iCal/GPX export
│── sentinel.py         # 🆕 DBSCAN clusters + velocity grading + Risk Pulse
│── companion.py        # Live Trip Companion — trips, alerts, broadcasts
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
3. **Itinerary** tab → keep the seeded five Goa stops (Start · Aguada ·
   Calangute · Anjuna · Baga) or tweak in the editor, choose
   `forecast-safest`, **Plan itinerary**. The 2-opt re-orders the stops,
   the Gantt timeline lays out the day, and `Itinerary iCal (.ics)`
   downloads a calendar you can drop into Apple/Google/Outlook.
4. **Sentinel** tab → on the seeded data the Risk Pulse should read
   **Critical** with 5 emerging hotspots (Calangute accidents, the
   southern landslide ridge, the Panaji corridor, the Baga sub-cluster
   and the Bambolim flooding micro-cluster). Open the parameter expander
   to widen ε to 1.0 km and watch the Calangute and Baga clusters merge
   into a single super-hotspot in real time. The **Watch banner** at the
   top of the Map tab mirrors the pulse status everywhere in the app.
5. **Live Trip** tab → pick `safest` (or `forecast-safest`), choose
   `4×` simulation, **▶ Start journey**.
6. Watch:
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

**Itinerary composite score**
```
score = clip(  Σ(km_i · avg_safety_i) / Σ km_i  −  6 · #(legs with min_safety < 35),  0, 100)
```

**Sentinel cluster velocity & status**
```
velocity = (recent_count/recent_days + ε) / (baseline_count/baseline_days + ε)   ε = 0.005

velocity ≥ 2.5   →  Critical          n_critical ≥ 1                  →  Pulse: Critical
velocity ≥ 1.3   →  Emerging          n_emerging ≥ 2                  →  Pulse: Active
0.6 ≤ v < 1.3    →  Steady            n_emerging ≥ 1 or n_steady ≥ 3  →  Pulse: Watch
velocity < 0.6   →  Cooling           otherwise                       →  Pulse: Calm
```

---

## 📍 Roadmap

- [x] Real safety intelligence engine + heatmap + dark UI (round 1)
- [x] Risk-aware A\* router + dual-route UI (round 2)
- [x] AI-powered hazard forecasting (round 3 opener)
- [x] **Live Trip Companion + trusted-contacts broadcast** (round 3 closer)
- [x] **Multi-stop itinerary chaining** (2-opt order + Gantt + iCal export, Day 21)
- [x] **Sentinel — live cluster intel + emerging-hotspot alerts** (DBSCAN + velocity grading + Risk Pulse, Day 26)
- [ ] Real-time push (web-sockets) instead of file-tail simulation
- [ ] Mobile-first PWA shell with native geolocation feed
- [ ] Live traffic / road-closure overlay (HERE or Mapbox)

---

## 👨‍💻 Author

Built with ❤️ by **Aryan D Haritsa** — Student @ PES University · Entrepreneur ·
AI · Full-stack · research.
