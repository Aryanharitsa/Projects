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
- **🆕 Travel Advisory brief** — the *one page* a tourist actually wants
  before walking out the door. For any destination (your current
  location, a POI, or a custom lat/lon) WaySafe fuses every engine in the
  repo — Safety Intelligence, Sentinel clusters, the forecast, geofences,
  POIs — into a single shareable brief with an **All clear / Caution /
  Elevated / Critical** advisory level, a per-incident timeline, a 7-day
  trend sparkline, the *safer depart windows* for the next 12 h, the five
  nearest help POIs and a ranked checklist of what to do. Exports as
  **PDF**, **JSON** (`waysafe.advisory.v1` schema) and **markdown** so it
  drops into a WhatsApp message, an email, or a printed handout for the
  family fridge. Live clusters that are escalating *force-bump* the
  advisory level — a static safety score won't reflect activity that's
  still in motion, so the advisory does.
- **🆕 Compass — Destination Showdown** — the *comparative* answer to
  "where should I go tonight?". Pick 2–5 candidates (curated Goa presets,
  your current location, or custom points) and Compass ranks them **at
  your depart time**, fusing the safety score, the depart-hour forecast,
  and live Sentinel cluster pressure into one forward-looking **Compass
  score** (0–100). It declares a winner with a margin ("Anjuna is the
  clear safe pick — 18 pts clear of Baga"), names the *deciding factor*,
  and lays every candidate out in a heat-mapped **comparison matrix** so
  the trade-offs are obvious at a glance. Exports as JSON
  (`waysafe.compass.v1`) and markdown.
- **🆕 StaySafe — Accommodation Safety Picker** — the *bookable*
  counterpart to Compass. Compass answers "where should I *go*?";
  StaySafe answers "where should I *sleep*?" — a fundamentally different
  question because you spend 16+ hours a day at your stay across the
  **sleep**, **evening-return** and **morning-depart** windows. Each
  candidate is scored on six time-aware dimensions (sleep / evening /
  morning forecast risk + walkability to nearest hospital, police and
  clinic + quiet score around the property + reach to the area's centre
  of gravity), the weights re-balance by **traveller profile** (Solo /
  Couple / Family-with-kids / Business-or-solo-F), and the verdict comes
  with a podium, a 24-hour risk **sparkline per stay**, a three-column
  *walk to help* breakdown for the winner, and a heat-mapped factor
  matrix that surfaces every dimension's weighted **points contribution**.
  Ships with a curated **15-stay Goa preset list** (hotels, resorts,
  hostels, homestays), takes custom lat/lon rows, and exports as JSON
  (`waysafe.staysafe.v1`) and markdown for WhatsApp/email.
- **🆕 Pulse — Today's Outlook** — the *morning-brief* surface that
  answers the question no other tab does: *"what's actually different in
  my day vs yesterday, and what should I do about it before lunch?"*
  Pulse treats your day as a portfolio of **watched points** — typically
  your stay plus 1–3 planned destinations — and re-runs every WaySafe
  engine for each point at **`now`** *and* at **`now − 24 h`**:
  `safety.compute_safety` (signed Δscore + band shift), `forecast.risk_curve`
  for today + the prior-day DOW (so a calm yesterday → restless today
  swing pops out), `sentinel.cluster_incidents` (which clusters intersect
  the day's plan within 1.5 km, escalating-first), and `refuge.find_refuge`
  (is the closest help POI still in a Strong / Viable band?). It then
  composes a single one-page brief: a **mood ring** (Calm / Watch /
  Active / Critical, picked from worst-band + cluster pressure + ≥2
  watched points slipping ≥10 pts), a **biggest-mover card** (signed
  Δscore on the point that swung most), a **24-hour joint risk ribbon**
  (`joint(h) = max_p curve_p(h)`) with the best 3-h **outdoor window**
  outlined in green and the worst outlined in red, **per-watched-point
  cards** (ring + delta chip + cluster pings + mini-curve + best-window /
  nearest-refuge side panel), a **Sentinel intersections** list, a
  ranked **"what changed since yesterday"** change log, and a prioritised
  **plan-of-day** checklist that references Tempo and the Map tab by name
  when those are the right follow-ups. Pulse is *pure composition* — it
  adds zero new physics; every number comes from an engine that already
  shipped. The *new* thing it brings to WaySafe is the **temporal-delta
  lens**: every other surface up to Day 55 was forward-looking; Pulse is
  the first surface that asks "what's different now than 24 hours ago",
  which is the signal that makes a daily brief actually worth opening.
  Exports as JSON (`waysafe.pulse.v1`) and markdown for the WhatsApp /
  email family-update loop. Lives at `tabs[0]` because this is what the
  traveller opens first thing in the morning. Pure-Python, zero new deps.
- **🆕 Beacon — Group Safety Coordinator** — every other WaySafe surface
  treats the traveller as a single point. Beacon is the first surface that
  thinks in terms of a **group** — 2–6 members (family, student trip,
  business team) who have temporarily split up and need to regroup
  *safely*, not just *somewhere*. Three engines stacked on top of the
  existing physics: (1) a **group composite** = `0.50·min_score +
  0.30·kind-weighted_mean + 0.20·spread_score` where `spread_score` falls
  linearly from 100 at ≤800 m max-pairwise-distance to 0 at ≥3.8 km — so
  a splintered group reads as *less coordinated* even if every member's
  individual score is fine; (2) a **meet-point ranker** that scores
  candidates by `0.40·safety_at_point + 0.25·(1 − worst_corridor_risk) +
  0.20·(1 − max_walk/4 km) + 0.15·(1 − sum_walk/(4·n))` — the chain is
  only as strong as its riskiest member-walk, and the slowest member
  dominates a real-world rendezvous, so both make the blend; candidates
  come from four sources (geometric centroid, top-5 help POIs within 4 km
  of centroid ranked by raw safety score, top-3 cells from a 5×5
  safe-grid sample, plus a *"stay with X"* fallback when one member is
  already in a Safe band); (3) **rendezvous corridors** sample 8
  waypoints from each member to the chosen meet-point and price each by
  `safety.point_risk` so the map paints them blue / amber / rose by peak
  risk and the alerts surface re-routes when peak ≥ 0.55. Mood ladder
  (first-match-wins): `Critical` if any member Danger or chosen worst
  corridor ≥ 0.65 · `Active` if any High Risk or spread > 2.5 km ·
  `Watch` if any Caution or spread > 1.2 km · else `Calm`. Per-member
  cards show ring + isolation chip + nearest-help chip + corridor
  distance/ETA/risk; meet-point table highlights the chosen pick green
  and the secondary amber so the analyst can see *why* one beat the
  other across all four factors; a prioritised plan-of-action references
  **Refuge**, **Live Trip**, and **Alerts** by name when those are the
  right follow-ups. Pure-stdlib + reuse of `compute_safety` and
  `point_risk` — zero new physics. Exports as JSON
  (`waysafe.beacon.v1`) and markdown for the squad chat. Lives at
  `tabs[1]` next to Pulse because both are *composer* surfaces — Pulse
  asks *"what changed?"*, Beacon asks *"where do we meet?"*.
- **🆕 Tempo — Departure-Window Optimizer** — the *temporal* layer that
  closes the loop on planning: **when** should you leave? Every other
  surface answers *where* (Compass), *where to sleep* (StaySafe), *how to
  get there* (Plan Route), or *where to flee* (Refuge). None answer the
  most common real-world question: *"I want to be at the destination
  between 17:00 and 19:00 — what's the optimal minute to leave?"*. Tempo
  sweeps the joint **(arrival_minute × route_flavor)** grid (safest ·
  balanced · fastest), runs the forecast-aware A\* once per cell, and
  scores each candidate by **integrated risk along the actual corridor**:
  `risk_km = mean(forecast_blended_risk along corridor) × distance_km`,
  composite `= 100·exp(−κ·risk_km)` with κ=0.35 (risk_km 0.64→80 ·
  1.23→65 · 1.98→50 · 3.0→35). The winner is the highest-composite
  feasible cell (depart ≥ now); ties broken by lower risk-km, then higher
  min-safety, then shorter ETA. **Comparisons** name three baselines —
  *depart-now*, *earliest arrival*, *latest arrival* — and quote the
  concrete Δrisk-km saved vs each. **UI**: a hero card with the chosen
  depart-time as a big ring (composite-filled, hue by band, with the
  *in 41 min* relative time below), a colour-coded **flavor × arrival
  heatmap** marking the winner with a glow ring and dimming cells whose
  depart-time is already in the past, a **comparison strip** of side-by-side
  cards (winner card glows, baselines show *−2 pts*, *+0.07 risk-km* deltas),
  a **rationale** block of plain-English bullets ("vs Latest arrival
  (18:41→19:00): winner saves 0.07 risk-km along the 9.9 km corridor,
  +2 pts on the composite"), a **runners-up** strip for the next-best two
  cells within 6 pts, and a **pydeck map** overlay of the winning corridor
  in green with runners-up faint. Exports as JSON (`waysafe.tempo.v1`)
  and markdown. Pure-Python, reuses `forecast.HazardForecaster`,
  `routing.plan_forecast_route`, and `safety.point_risk` — Tempo's
  verdict always agrees with the safest-A\* path at the chosen depart.
- **🆕 Refuge — "Get Me to Safety" engine** — the missing *egress* layer
  that answers the only question that matters when something feels wrong
  *right now*: **where do I go in the next five minutes?** The previous
  SOS tab was a placeholder — flip a flag, show the three closest help
  POIs sorted by raw great-circle distance. That ranking is wrong in the
  moments it matters. Refuge ranks every help POI inside the scan radius
  by a deterministic composite **Refuge Score** — *proximity 35% · path
  safety 25% · trust tier 20% · open-now 15% · corridor crowd 5%* — and
  surfaces a bearing-compass hero ("Head **SSW** · police in **178 m**"),
  per-tier arrival scripts (*"walk to triage and tell them you don't feel
  safe"* for hospitals; *"ring the night-bell at the gate"* for fire
  stations), a 5-step **corridor heat-strip** showing path safety along
  the great-circle line to each option (dashed outline = waypoint inside
  a geofenced risk zone), and a country-specific **emergency-card**
  quick-dial (India 100/101/102/1091/1363 · EU 112 · US/CA 911). A
  one-tap **Quiet Beacon** writes a broadcast row keyed to the top refuge
  and produces a ready-to-send SMS payload with a walking Google-Maps
  deeplink — designed for the threat model where a visible panic button
  makes things worse. Pure-stdlib + reuses `safety.point_risk`, so Refuge
  agrees with the safest-A\* router on which corridors are good.
- **Sentinel — Live Cluster Intel** — DBSCAN over haversine groups raw
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

## 🧭 Travel Advisory — pre-trip brief (Day 31)

The Advisory tab takes one (lat, lon) — your current location, a POI from
the dataset, or a custom point you type in — and produces a single-page,
shareable safety brief. It's the *answer-in-30-seconds* surface for the
four questions every tourist actually asks before a trip:

1. **Is it safe to go right now?** — `All clear / Caution / Elevated / Critical`
2. **Why?** — recent incidents within scan radius, ranked by recency × severity
3. **When would be safer?** — top-3 lowest-risk depart windows in the next 12 h
4. **Where is the nearest help if it goes wrong?** — top-5 ranked help POIs

### Advisory level

```
safety score 80..100  →  All clear   (#10B981)
safety score 60..79   →  Caution     (#FBBF24)
safety score 35..59   →  Elevated    (#F59E0B)
safety score  0..34   →  Critical    (#EF4444)
```

The level is then *force-bumped* if Sentinel sees escalating clusters
overlapping the scan disc:

```
≥ 2 severe clusters (Critical/Emerging + severity_mean ≥ 3.5)  →  Critical
≥ 1 severe cluster but base level == All clear                 →  Elevated
```

Static scoring alone can't see "things are moving"; the bump folds the
*velocity* signal in so the advisory matches what's happening on the
ground rather than what's already happened.

### What the brief contains

- A **hero card** with a conic-gradient score ring, the advisory level
  stripe and a one-line headline tailored to the level.
- Four **KPI tiles**: incidents nearby, live clusters near here, the
  safer depart window, and the nearest help POI.
- A **recent-incidents** list with severity dots, distance, age, status
  (verified / pending) and a short note.
- A **7-day incident trend** sparkline aligned to weekdays.
- **Live clusters near here** — Sentinel pills with edge distance,
  radius and days-since-last.
- **Safer depart windows** — top-3 lowest-risk hours in the next 12 h,
  pulled from the same `forecaster.hotspots(...)` engine the Forecast
  tab uses.
- **Nearest help** — top-5 hospitals / police / clinics / fire / tourist
  help-desks with distance.
- A numbered, prioritised **recommendations** checklist tailored to the
  advisory level, the geofence membership, the cluster mix, and the
  time-of-day.

### Exports

| Format | Use |
|---|---|
| **PDF** (`reportlab`) | colour-stripe header, two-column factor + help layout, incident list with notes, cluster row, recommendations checklist — print or attach |
| **JSON** | stable `waysafe.advisory.v1` schema — diff two briefs, store in a CRM, embed in a chatbot |
| **Markdown** | drop into a WhatsApp / email / Notion page in one paste |

Engine in `advisory.py` (≈540 LOC, pure-stdlib + reuse of every other
project module + `reportlab` for the PDF only). UI render lives in
`theme.render_advisory_brief`.

---

## 🧭 Compass — Destination Showdown (Day 36)

The Advisory answers *"is **this** place safe?"*. But tourists rarely have
one fixed destination — they choose between options. Compass answers the
**comparative** question: *Baga or Anjuna for dinner? Stay in Calangute or
move to Panaji?* It runs every engine over 2–5 candidates **at your depart
time** and returns one ranked verdict.

### Compass score

```
compass = clip( safety_score
                − 16 · forecast_risk_at_depart      (0..1 → up to −16)
                − cluster_penalty ,                  (capped at −20)
                0, 100 )

cluster_penalty = Σ over overlapping clusters  status_weight · (severity_mean / 5)
   status_weight:  Critical 12 · Emerging 6 · Steady 2 · Cooling 0
```

The safety score is a static snapshot. The **forecast term** prices *when*
you're going (a calm beach at 3 PM is not the same beach at 2 AM). The
**cluster term** folds in Sentinel's *velocity* — an escalating hotspot
drags a destination down even when its historical score looks fine. The
advisory level shown per card uses the same thresholds (and the same
"escalating clusters force-bump" rule) as the Advisory tab, so the two
surfaces never disagree.

### What the showdown contains

- A **verdict hero** — the winner's Compass ring, the headline
  (`clear safe pick` / `edges it` / `just shades it` / `neck-and-neck`
  scaled by margin), the *deciding factor* ("wins mainly on nearest
  help"), and a margin badge.
- A **podium** of ranked cards — gold/silver/bronze rank badge, advisory
  pill, a Compass-score bar coloured red→amber→green, and three mini-stats
  (incidents nearby · nearest help km · depart-hour forecast %).
- A heat-mapped **comparison matrix** — destinations as columns, factors
  as rows (Compass score, Safety score, Forecast risk, Incidents nearby,
  Nearest help, Live clusters). Every cell is coloured by *goodness*
  (greener = safer) so the trade-offs read at a glance, with the winner's
  column highlighted.
- A **"why each destination scored that way"** drill-down with the raw
  safety factor breakdown and the safer hour to visit *that* spot.

### Exports

| Format | Use |
|---|---|
| **JSON** | stable `waysafe.compass.v1` schema — full per-destination breakdown + verdict |
| **Markdown** | a verdict + leaderboard table + per-destination notes, one paste into WhatsApp / email / Notion |

Engine in `compass.py` (≈460 LOC, pure-stdlib + reuse of `safety`,
`forecast`, and `sentinel`). UI render lives in `theme.render_compass`.

---

## 🛏️ StaySafe — Accommodation Safety Picker (Day 41)

Compass and StaySafe are the same shape — pick candidates, get a podium
+ a heat-mapped matrix — but the *physics* is different. A destination
visit is a single point in time; a stay is **16+ hours every day** at
the same address, so the score has to be time-of-stay weighted.

The StaySafe tab takes a multiselect over a curated 15-stay Goa preset
(hotels, resorts, hostels, homestays — `data/stays.csv`), takes any
number of custom (name, lat, lon, kind) rows you add, asks for your
**check-in date/time**, **nights**, and **traveller profile**, and
returns a ranked verdict.

### Six dimensions, weight-aware

Each candidate is scored along six 0..1 sub-dimensions; the
composite is the weighted sum × 100. The window terms are computed by
blending the **temporal forecast** (`forecaster.risk_at`) with the
**static physics** (`safety.point_risk`) at 45 / 55 so a stay that's
surrounded by recent verified incidents is *always* downgraded even
if the forecaster has no late-night history for that cell.

| Dim | What it measures | Default w | Why |
|---|---|---:|---|
| `sleep` | mean risk 22:00 → 06:00 on check-in date | **0.30** | Largest exposure window |
| `evening` | mean risk 19:00 → 22:00 | 0.20 | Walking back from dinner |
| `morning` | mean risk 06:00 → 09:00 | 0.10 | Stepping out fresh |
| `walkability` | mean of (hospital / police / clinic) walk-distance goodness, ceiling 4 / 2 / 1.5 km, gracefully degrades to 2-of-3 when the dataset has no clinic | 0.18 | "How far is help if it goes wrong?" |
| `quiet` | inverse Sentinel cluster pressure within **0.8 km**, with night-active clusters (peak hour ∈ [20..3]) carrying a 1.6× multiplier | 0.12 | Loud-at-night hotspots can't hide |
| `reach` | U-shaped score around the trip's centre of gravity (mean of the candidates) — sweet spot 1.5 km, full penalty under 0.2 km or beyond 6 km | 0.10 | Not too isolated, not crowded |

If the stay sits inside a geofenced **risk zone**, the composite is
floored to Elevated (score ≤ 59) regardless of the per-window math —
the static safety reflects this but the composite is forecast-heavy,
so we force the floor.

### Traveller profiles re-balance the weights

| Profile | sleep | evening | morning | walk | quiet | reach |
|---|---:|---:|---:|---:|---:|---:|
| Solo traveller | 0.32 | 0.24 | 0.08 | 0.18 | 0.10 | 0.08 |
| Couple | 0.30 | 0.20 | 0.10 | 0.18 | 0.12 | 0.10 |
| Family with kids | 0.28 | 0.18 | 0.10 | **0.22** | **0.16** | 0.06 |
| Business / solo F | **0.34** | 0.22 | 0.10 | 0.18 | 0.10 | 0.06 |

### Verdict surface

```
Recommend Vivanta Goa Panaji — 14 pts clear of Lemon Tree Amarante Candolim.
Vivanta Goa Panaji wins mainly on walk to help.
```

The render stack includes:

- **Hero card** with the winner's 0–100 ring, level chip, profile chip,
  check-in / nights / "N stays compared" meta, and a `+pts ahead` margin.
- **Podium row** of stay cards — rank chip, kind chip, level chip, score
  bar, sleep / evening / morning tri-cell mini-stats, a **24-hour risk
  sparkline** (one bar per hour, hue and height encode risk), the
  headline blurb and a one-line *why pick* rationale tailored to the
  actual numbers (e.g. *"Hospital 1.2 km away; calm sleep window."*).
- **Walk-to-help** breakdown for the winner: three cards (hospital /
  police / clinic) with name, distance + walk-time at 4.8 km/h, and a
  goodness bar.
- **Heat-mapped factor matrix** — destinations as columns, factors as
  rows, every cell hue-coded green↔red by that factor's goodness, with
  a sub-text inside each cell showing the **weighted points
  contribution** to the composite so users can see *which* dimension is
  driving the score, not just that it does.
- A **per-stay text breakdown** in an expander.
- **JSON** (`waysafe.staysafe.v1`) and **markdown** exports.

Engine in `stays.py` (≈580 LOC, pure-stdlib + reuse of `safety` and
`forecast`). UI render in `theme.render_staysafe`. Preset data in
`data/stays.csv` (15 Goa stays).

---

## 🆘 Refuge — "Get Me to Safety" engine (Day 46)

Every other WaySafe surface is a *planning* surface. Refuge is the
*egress* surface — the one that fires when a tourist's plan has already
broken. The pre-existing **SOS** tab in the app was a placeholder: it
flipped a `sos_active` flag and listed the three closest help POIs by raw
great-circle distance. That ranking is *wrong* in the only moments it
matters:

- A hospital 400 m away through an unlit, geofenced corridor is **worse**
  than a 24/7 store 600 m away on a busy main road.
- A fire station that's gated at midnight is **worse** than a police
  chowki 200 m further that's actually staffed.
- A hotel front desk is a refuge **only** if it's 24/7-attended.
- Trust tiers exist: police > hospital > embassy > fire > tourist help
  desk > 24/7 retail > hotel front desk > 24/7 petrol pump.

Refuge replaces the broken ranking with a deterministic composite **0–100
Refuge Score**:

```
refuge = 100 · ( 0.35 · proximity
               + 0.25 · path_safety
               + 0.20 · trust_tier
               + 0.15 · open_confidence
               + 0.05 · crowd_proxy )
```

| Factor | What it measures | Why it matters |
|---|---|---|
| `proximity` | linear: 1.0 at 0 km → 0.0 at `max_radius_km` | The cheapest fix first — closer is always better, all else equal |
| `path_safety` | mean of `1 − safety.point_risk` across **5 evenly-spaced waypoints** on the great-circle line from you to the candidate | Reuses the exact physics the safest-A\* router uses, so Refuge agrees with the route planner on which corridors are good |
| `trust_tier` | institutional weight, police 1.00 → 24/7 petrol 0.50 | A police station is intrinsically a stronger refuge than a 24/7 store even at the same distance |
| `open_confidence` | 1.0 for 24/7 tiers (police, hospital ER, fire, 24/7 store, 24/7 petrol). Tourist help-desks & clinics degrade to 0.25 outside `open_window`; hotel front desks hold 0.85 at night | Refuges you can't enter aren't refuges |
| `crowd_proxy` | 1.0 if any non-help POI sits within 0.5 km of the corridor midpoint, else 0.0 | A rough proxy for *populated, well-lit main road* vs *dark lane* |

### Tiers

| Key | Weight | 24/7? | Arrival script |
|---|---:|---:|---|
| `police` | **1.00** | ✓ | "Walk in. Ask for the duty officer. Show this screen for your location & beacon ID." |
| `embassy` | 0.95 | ✗ (09–18) | "Show passport at the security booth. After-hours: ring the consular night line." |
| `hospital` | 0.92 | ✓ | "Walk to Emergency / Casualty. Tell triage you don't feel safe — they will hold you in waiting." |
| `fire` | 0.85 | ✓ | "Ring the night-bell at the gate. Crews are bunked on-site — someone always answers." |
| `tourist_help_desk` | 0.78 | ✗ (08–21) | "Hand over your passport copy. They have direct tourist-police hotlines." |
| `clinic` | 0.62 | ✗ (08–22) | "Reception desk. Most clinics will let you wait inside until conditions change." |
| `allnight_store` | 0.62 | ✓ | "Walk in, buy something cheap, sit by the counter. Ask the cashier to call a cab." |
| `hotel` | 0.55 | ✓ (front desk) | "Tell the night manager you need sanctuary. Show a booking on your phone if you have one." |
| `petrol_24h` | 0.50 | ✓ | "Walk to the attendant booth. Ask to wait while you call someone." |

### Refuge bands

```
refuge 72..100  →  Strong refuge   (#10B981)
refuge 55..72   →  Viable refuge   (#FBBF24)
refuge 35..55   →  Last resort     (#F59E0B)
refuge  0..35   →  Not a refuge    (#EF4444)
```

### What the Refuge tab surfaces

- **Bearing-compass hero** — a 168 px conic ring whose stroke colour
  encodes the top refuge's band and a centred arrow rotated to the
  initial great-circle bearing from you to the top refuge ("↑ SSW · 178°
  · 98/100"). Headline reads as a one-liner you can act on without
  reading the rest of the page: *"Head SSW · police station in 178 m
  (2 min on foot)."*
- **Local-spot pill** in the hero — your *current location's* safety
  score on the right edge of the card. If your spot is **Danger** or
  **High Risk**, the advisory line escalates to *"You're standing in a
  high-risk zone (score 46/100) — move now."*
- **Podium of up to 8 options**, each card stamped with:
  - Tier icon + label, name, refuge score, band chip, score bar.
  - Three mini-stats: distance (m), walk-time (min @ 5 km/h), heading
    (cardinal label like "ENE").
  - **5-step corridor heat-strip** — one bar per waypoint, hue-coded
    from `1 − point_risk`, with a *dashed red outline* on any waypoint
    that falls inside a geofenced risk zone. This is the rare UI element
    that lets a user *see* whether the path from here to there cuts
    through a bad area.
  - Per-tier **arrival script** (one line, italic) so the user knows
    what to do the moment they walk in.
  - Up to 3 notes: *"corridor clips 1 risk-zone waypoint"*, *"quiet
    corridor — no other POIs near midpoint; walk briskly"*, *"clinic
    normally closes by 22:00 — expect a locked main door, ring the
    night-bell or call before walking up"*, etc.
- **Heat-mapped factor matrix** — options as columns, factors as rows,
  every cell hue-coded by goodness so the trade-off is visible at a
  glance (the closest option that has the worst path? the bright cell
  tells you). Per-row weight chip surfaces the composite weights.
- **Country emergency card** — pre-localised quick-dial. Selection is
  by lat/lon: India (6–37° N, 68–98° E) → 100 / 101 / 102 / 1091 / 1363
  / 108 with a note that 112 works as the unified emergency number EU
  → 112. US/Canada → 911 + poison control + 988. Fallback → 112/911.
  Renders even in the fallback case (no POI in radius) — phone numbers
  always work.
- **Quiet Beacon** — a ready-to-copy SMS payload string and a **walking
  Google Maps deeplink** to the top refuge. A second button writes a
  broadcast row keyed to the top refuge into `data/broadcasts.csv` (or
  the offline outbox), reusing the existing Companion broadcast
  contract so trusted contacts get a ping with the refuge target.
  Designed for the threat model where a *visible* panic button makes
  things worse — no audio, no flashing.

### Fallback (no POI in radius)

If `find_refuge` returns zero candidates, the engine still:

1. Renders the user's own safety score and a single-line advisory
   ("No registered help POI within scan radius. Use the emergency card
   below. Move toward main-road traffic until you find lit, populated
   space.")
2. Renders the country emergency card — phone numbers don't depend on
   POI density.

### Data additions

`data/poi.csv` now ships 32 POIs spanning every Refuge tier — hospitals,
clinics, police stations & chowkis, fire stations & outposts, tourist
help desks, 24/7 supermarkets and 24/7 petrol pumps — across Panaji,
Calangute, Candolim, Anjuna, Vagator, Mapusa and Margao. This is what
makes the tier-diversity in the ranking visible: the top-5 at Calangute
on a Saturday night reads *police → fire → 24/7 store → 24/7 petrol →
(closed) tourist office*, not five hospitals in different directions.

Engine in `refuge.py` (≈540 LOC, pure-stdlib + reuse of `safety.point_risk`
and `utils.haversine_km`). UI render in `theme.render_refuge`. Test the
hour-aware open-confidence by un-checking *"Use current hour"* and
sliding to 23:00 — the tourist help-desk and clinic drop out of the
podium.

---

## 🛟 Beacon — Group Safety Coordinator (Day 61)

Every other WaySafe surface treats the traveller as a single point. **Beacon
is the first surface that thinks in terms of a group** — a family, a student
trip, a business team, a tour party of 2–6 people who have temporarily split
up and need to regroup *safely* (not just *somewhere*). Beacon answers three
questions a single-point engine can't:

1. **How is the group as a whole doing right now?** Not just the worst
   member, not just the average — a composite that penalises *spread*
   (a group whose members are 4 km apart is materially less coordinated
   than the same members 200 m apart, even at identical individual scores).
2. **Where should we meet?** Not the centroid (that's a geometric trick
   that ignores risk) and not the nearest help POI (that's only safe if
   the *paths* to it are safe). Beacon evaluates four candidate sources
   and ranks them by a four-factor blend.
3. **What's the per-member plan?** For the chosen meet-point we draw a
   rendezvous **corridor** from each member, sample 8 waypoints, price
   each by `point_risk`, and surface per-member alerts — who's in danger,
   who's most isolated, whose corridor crosses a geofence.

### How it composes

| Stage | Formula | Notes |
|---|---|---|
| Per-member score | `compute_safety(lat, lon, …)` | Same physics as the rest of WaySafe. |
| Per-member isolation | `min_{j ≠ i} haversine(i, j)` | Surfaced as a chip on every member card. |
| Group spread | `max_{i, j} haversine(i, j)` | The classic "fragmentation" proxy. |
| Spread penalty | `0.0` if ≤ 0.8 km, `1.0` if ≥ 3.8 km (linear) | Tunable in `beacon.SPREAD_FREE_KM` / `SPREAD_FULL_KM`. |
| **Group score** | `0.50·min_member + 0.30·kind-weighted_mean + 0.20·(100·(1 − spread_penalty))` | Weighted mean uses `KIND_WEIGHT` (`minor`=1.25, `elder`=1.20, `guide`=0.90, others=1.00). |
| **Group band** | `Safe / Caution / High Risk / Danger` from group score | Same `_band` thresholds as `safety.compute_safety`. |
| **Mood** ladder | first match wins, `Critical > Active > Watch > Calm` | See rules below. |

### Meet-point candidate sources

| Source | How many | What it adds |
|---|---|---|
| `centroid` | 1 | The geometric "fair" pick — useful when the group is loosely scattered. |
| `help_poi` | top-5 within 4 km of centroid | Institutional refuges (police, hospital, fire, clinic, tourist help-desk) ranked by raw `compute_safety` score so we don't waste a slot on a gated hospital next to a midnight roadblock. |
| `safe_pocket` | top-3 from a 5×5 grid centred on the centroid | Catches off-beat safe corners that aren't near any institutional refuge. |
| `stable_member` | 0–N | A member who's already in a Safe band becomes a candidate (`"Stay with X"`) — sometimes the best move is to **not** make everyone walk. |

### Meet-point score

```
score = 100 · (
    0.40 · safety_at_point/100
  + 0.25 · (1 − max_path_risk)        # the chain is only as strong as
                                       # its riskiest member-walk
  + 0.20 · (1 − min(1, max_walk / 4 km))   # slowest member dominates a
                                            # real-world rendezvous
  + 0.15 · (1 − min(1, sum_walk / (4 km · n))) # load-shedding bonus
)
```

`safety_at_point` is `compute_safety` at the candidate. `max_path_risk` is
the worst `point_risk` across 5 waypoints sampled along the great-circle
line from *every* member to the candidate. `max_walk` is the haversine
distance of the slowest member; `sum_walk` of everyone combined.

### Mood ladder (first-match-wins)

- **Critical** — any member in `Danger`, **or** group score < 35, **or**
  the chosen meet-point's worst corridor risk ≥ 0.65.
- **Active** — any member in `High Risk`, **or** group score < 60,
  **or** group spread > 2.5 km.
- **Watch** — any member in `Caution`, **or** group score < 80, **or**
  group spread > 1.2 km.
- **Calm** — otherwise.

### Biggest concern

The member that maximises:
`band_weight + max(0, isolation_km − 2.5) · 10 + max(0, 70 − score) · 0.4 + 8·(kind ∈ {minor, elder})`
where `band_weight ∈ {Danger:60, High Risk:40, Caution:20, Safe:0}`.

### Rendezvous corridors

For the chosen meet-point we sample **8 waypoints** from each member's
position to the meet-point (linear interpolation — at Goa-scale corridors
≤ 4 km, this matches the great-circle line to within ~1 m), price each by
`safety.point_risk`, and emit a `Corridor` with `mean_risk`, `peak_risk`,
distance, and ETA at a `4.5 km/h` walking pace. Corridors with peak risk
≥ `0.55` get a *risky* flag, which feeds the alerts panel and the map's
risk-graded `PathLayer` (blue / amber / rose).

### What you see

- **Hero** — group ring (mood-tinted hue, conic gradient, breathing animation)
  with the mood eyebrow + group score + group band; headline ("Critical ·
  Sister (minor) needs immediate help — group score 53 (High Risk)"); a
  *biggest concern* card on the right with the member glyph, band pill, and
  isolation + nearest-help summary.
- **Four-tile strip** — Group band · Group spread (km, hue-ramped) · Mood
  (+ alert count + candidate count) · Meet at (chosen label + slowest-member
  ETA + max walk).
- **Per-member cards** — score ring + kind glyph + label + isolation chip +
  nearest-help chip (hue-ramped) + corridor distance/ETA/risk chips
  (hue-ramped by peak risk) + band chip.
- **Meet-point table** — ranked candidates with the chosen pick highlighted
  green and the secondary highlighted amber. Each row shows source pill,
  composite score, safety at point, max walk, sum walk, worst corridor risk.
- **Group map** (`pydeck`) — members as band-colored `ScatterplotLayer`,
  meet-point as a gold star, corridors as a `PathLayer` painted blue / amber
  / rose by peak risk.
- **Alerts** — severity-banded cards (rose for Danger / High Risk lines,
  amber for isolation / geofence lines, yellow for corridor warnings,
  blue for informational).
- **Plan of action** — numbered checklist that references **Refuge**,
  **Live Trip**, and **Alerts** by name when those are the right
  follow-ups, plus a fallback meet-point line and a re-Beacon cadence
  reminder.
- **Exports** — JSON (`waysafe.beacon.v1`) and Markdown for the squad
  chat / WhatsApp loop.

### Why this matters

A single-point safety engine assumes the traveller *is* the unit of
analysis. The moment two or more people are on the same trip, that
assumption breaks: the question is no longer *"am I safe?"* but *"are
**we** safe, and what do we do *together* about it?"*. Beacon closes
that gap with the same composer DNA as Pulse (Day 56), SynapseOS Pulse
(Day 59), and TITAN Pulse (Day 60) — every number on the screen comes
from an engine that already shipped; the **group lens** is the new
thing.

---

## 💓 Pulse — Today's Outlook (Day 56)

Every WaySafe surface up to Day 55 is a *forward-looking* planner —
Compass picks *where* to go, StaySafe picks *where to sleep*, Plan Route
picks *how* to get there, Tempo picks *when* to leave, Refuge picks
*where to flee*. None of them answer the question a traveller asks the
*moment they wake up*:

> "What's different in my day than it was 24 hours ago, and what
>  should I do about it before lunch?"

Pulse is that surface. It treats your day as a small portfolio of
**watched points** — typically your stay plus 1–3 planned destinations —
and re-runs every WaySafe engine for each point at **`now`** *and* at
**`now − 24 h`**, then ranks the resulting deltas into a single one-page
brief. Pulse adds **zero new physics**; every number on the screen comes
from an engine that already shipped. The *new* thing it brings is the
**temporal-delta lens** — the change-since-yesterday signal that makes a
daily brief actually worth opening.

### What gets re-run per watched point

| Engine | What Pulse asks it twice | New signal |
|---|---|---|
| `safety.compute_safety` | score at `now` (full incident set) **and** at `now − 24 h` (filter out incidents created after the cutoff) | signed Δscore + band-shift flag |
| `forecast.HazardForecaster.risk_curve` | 24-h curve for **today's** DOW + 24-h curve for **yesterday's** DOW | curve diff (mini ribbon per point) |
| `sentinel.cluster_incidents` | the cluster set is computed once globally — Pulse picks the ones whose halo edge sits within **1.5 km** of the watched point | per-point cluster pings, escalating-first |
| `refuge.find_refuge` | top option band & distance for the stay | "refuge readiness" tile |

### How the day-level summary is built

```
joint_curve[h]            = max_p forecast.risk(p, today, h)
best_outdoor_window       = argmin over h of mean(joint_curve[h : h+3])
worst_outdoor_window      = argmax over h of mean(joint_curve[h : h+3])
overall_band              = worst band across watched-point bands
overall_mood              = Critical / Active / Watch / Calm
                            (rules below — first match wins)
```

**Mood rules** (first match wins, so the worst signal sets the tone):

- **Critical** — any watched point Danger, or any intersecting cluster Critical.
- **Active**   — any watched point High Risk, or any cluster Emerging, or
  ≥ 2 watched points slipped ≥ 10 pts in 24 h.
- **Watch**    — any Caution band, or any point dropped ≥ 5 pts.
- **Calm**     — otherwise.

**Biggest mover** is the watched point that maximises a *signal* score:
`|Δscore| · 1.0  +  new_incidents_24h · 4.0  +  Σ_escalating-clusters (6 + 2·(velocity−1))  +  6·band-shift  +  4·(refuge band ∈ {High Risk, Danger})`.

### What you see

- A **hero card** — left ring shows the mean watched-point score, mood
  pill, mood-tinted glow. Headline is one sentence ("Critical morning ·
  Baga beach down 21 pts · best window 03:00–06:00"). Right card calls
  out the biggest mover with signed Δscore and a band arrow
  (Caution → High Risk).
- A **four-tile strip**: overall band · best 3-h outdoor window · total
  new incidents within 1 km in the last 24 h · refuge readiness at the
  stay (band + nearest POI + distance).
- A **24-hour joint risk ribbon** — one row of 24 cells coloured by
  `joint_curve(h)`, with the best window outlined in green, the worst
  outlined in red, and a blue line marking the current hour. Past
  hours dim to 35% opacity.
- A **per-watched-point card** — score ring, kind chip (stay /
  destination / custom), band, Δ-chip ("▼ −21 pts vs 24h ago"), cluster
  pings (escalating ones go red), a band-shift chip when the band moved,
  a plain-English changes block, a compact today-curve mini-ribbon, and
  a side panel with the point's own best 3-h window and nearest refuge.
- A **Sentinel intersections** list — de-duped across watched points,
  closest-first within each escalation tier, escalating-first overall.
- A ranked **"what changed since yesterday"** list — every per-snapshot
  change line sorted by signal magnitude so the biggest-mover's lines
  float to the top.
- A prioritised **plan-of-day** checklist that references *Tempo* and
  *Map* by name when those are the right follow-ups
  ("Re-plan any leg through Cluster #1 — pick a corridor ≥ 1.5 km away
  and prefer the Tempo winner over a now-departure.").
- **Exports** — JSON (`waysafe.pulse.v1`) and markdown for the WhatsApp
  / email family-update loop.

### Why this matters

A planner suite that only ever computes "what is" leaves the traveller
to track "what changed" in their head. Pulse closes that loop. On a calm
day it says so in one line and lets the user move on; on a day where a
Sentinel cluster has crossed Critical velocity overnight, it surfaces
the exact watched-point that touches it, names the cluster, quotes the
edge distance, and tells the user which other WaySafe tab to open next.
This is the surface a traveller opens *first* — which is why it now lives
at `tabs[0]`.

Pure-Python, zero new deps. Pulse is the first WaySafe surface that
*has no engine of its own* — it's a composer. That's the point.

---

## ⏱ Tempo — Departure-Window Optimizer (Day 51)

Every other surface in WaySafe answers a *spatial* question — where to
go, where to sleep, how to get there, where to flee. The most common
real-world planning question is *temporal*:

> "I want to be at the destination between 17:00 and 19:00 today —
>  when should I leave, and which route flavor should I take?"

The forecaster has `find_best_window` (pointwise sweep around one cell)
and the router has `find_best_departure` (sweep one alpha around one
depart-time). Neither models the corridor; neither sweeps route flavors;
neither anchors the search to a *target arrival window* with feasibility
constraints. Tempo is the optimisation + UX layer that does.

### Physics

For each `(arrival_t, alpha)` in the grid:

```
eta_alpha = baseline ETA for that alpha (probed once at window midpoint)
depart_t  = arrival_t − eta_alpha
route     = plan_forecast_route(origin, dest, forecaster, depart_t, alpha)
risk_km   = mean(forecast_blended_risk along corridor) × distance_km
composite = 100 × exp(−κ · risk_km)        # κ = 0.35
band      = All-clear ≥80 · Caution 65 · Elevated 50 · High Risk 35 · Danger <35
```

`risk_km` is the integrated exposure the traveller *actually* absorbs on
the corridor at that time — it folds in distance, hour-conditional
forecast, geofences and live-incident proximity into one number. The
exponential keeps the curve gentle for small differences (so a 0.1 risk-km
gap doesn't flip the band) and steep for big ones.

Calibration check:

| `risk_km` | composite | band      |
|----------:|----------:|:----------|
| 0.00      | 100       | All-clear |
| 0.64      |  80       | All-clear |
| 1.23      |  65       | Caution   |
| 1.98      |  50       | Elevated  |
| 3.00      |  35       | High Risk |

### Selection

- **Winner** = highest composite among **feasible** cells (where
  `depart_t ≥ now`). Ties broken by lower `risk_km`, then higher
  `min_safety`, then shorter ETA.
- **Runners-up** = next-best two distinct (arrival, flavor) cells within
  6 pts of the winner.
- **Infeasible** cells (depart in the past) are still scored and dimmed
  in the grid with a diagonal-stripe pattern, with a count footnote
  ("3/30 cells would require leaving in the past").

### Comparisons — three baselines

Every Tempo result names the winner *and* three baselines on the same
flavor for an honest comparison:

| Baseline | Definition |
|---|---|
| **Depart now** | Same-flavor cell whose `depart_t` is closest to `now` |
| **Earliest arrival** | First arrival slot in the window |
| **Latest arrival** | Last arrival slot in the window |

Each carries `Δcomposite = winner − baseline` and `Δrisk_km = baseline −
winner`. The rationale lines quote them directly:

> *"vs Latest arrival (18:41→19:00, composite 88): winner saves 0.07
>  risk-km along the 9.9 km corridor, +2 pts on the composite."*

When a baseline coincides with the winner (e.g. depart-now happens to be
optimal), it's flagged "≈ tie with winner".

### Cross-flavor rationale

If at the winner's arrival minute a *different* flavor would have scored
within 4 pts, Tempo says so explicitly — that tells the user routing
choice barely moves the needle here, and they can pick by preference. If
the gap is wider, the rationale surfaces it: *"At 00:15, the **safest**
flavor beats **fastest** by 6 pts (87 vs 81) — routing matters more than
departure timing here."*

### What the Tempo tab surfaces

1. **Hero card** — winner depart-time as a big composite-filled ring
   (hue by band), the relative `in 41 min`, the destination + arrival
   time on the right, a flavor pill with glyph (🛡 safest · ⚖ balanced ·
   🏁 fastest), and a meta strip with ETA, distance, risk-km, avg/min
   safety, and any warm-stretch warning.
2. **Heatmap grid** — rows = flavors, cols = arrival slots, each cell
   coloured by its band hue at score-proportional alpha; **winner cell
   ringed and starred**, infeasible cells dimmed with a 135° stripe
   pattern. Sub-label inside each cell shows the implied depart-time.
   A legend strip at the bottom maps colours to bands.
3. **Comparison strip** — side-by-side cards for **Winner / Depart-now /
   Earliest / Latest**. Winner card has a coloured glow; baselines show
   `▼ −2 pts · +0.07 risk-km vs winner` deltas in band-coloured chips.
4. **Rationale block** — bulleted plain-English explanations of why this
   minute beats each baseline, with concrete numbers and a forecast
   pocket call-out when relevant.
5. **Runners-up** — next-best two cells within 6 pts as compact cards
   (rank badge · times · composite · band · risk-km · distance).
6. **Winner-corridor preview** — pydeck map with the winning route in
   green and runners-up corridors faint grey, plus origin (blue) and
   destination (orange) markers.
7. **Exports** — JSON (`waysafe.tempo.v1` schema, includes the full grid
   for reproducibility) and a markdown digest for WhatsApp / email /
   Notion paste.

### What it adds over existing surfaces

| Existing | Question it answers | Gap Tempo fills |
|---|---|---|
| `Forecast.find_best_window` | Risk-vs-time at *one cell* | Doesn't model the corridor; doesn't sweep route flavors |
| `routing.find_best_departure` | Sweep depart-times for *one* alpha | One flavor only; ranks by avg/min safety, not exposure; no arrival anchoring |
| `Compass` | Which destination is safest right now | Spatial only — doesn't move in time |
| `Plan Route` | Best corridor *given* a depart-time | The depart-time is an input, not optimised |

Tempo is the **optimisation layer** that uses the existing engines as
oracles. Zero new physics: it reuses `plan_forecast_route` (which itself
reuses `safety.point_risk` and `HazardForecaster.risk_at`), so Tempo's
verdict is always consistent with the safest-A\* corridor at the chosen
depart-time.

### Headline demo — Panaji → Calangute, arrive between 17:30–19:00

On the bundled `incidents.csv` with the corridor seed, anchored at
`now = Fri 16:30`:

- Winner: depart **17:11** → arrive **17:30**, safest flavor, composite
  **90/100 · All-clear**, risk-km **0.30** along a 9.9 km corridor.
- Heatmap: **safest** and **balanced** rows hover at 88–90 across the
  window; **fastest** row sits flat at 79 — *"routing matters more than
  departure timing"* is a one-glance read.
- Comparison: depart-now is identical to the winner (anchor is 36 min
  before depart, the closest depart-slot in the window is 17:11 itself);
  latest-arrival (18:41→19:00) scores 88, +2 pts behind the winner.
- Rationale: *"Destination cell sits in a quiet forecast pocket at 17:30
  (0.01) — that pocket is why this slot wins."*

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
│── app.py              # Streamlit shell — Tourist / Authority / Auditor roles, 12 tabs
│── safety.py           # Live 0–100 score + heatmap weights + point_risk()
│── routing.py          # A* over priced grid + GPX + forecast-aware variant
│── forecast.py         # Empirical-Bayes spatiotemporal hazard model
│── itinerary.py        # Multi-stop planner — 2-opt order + iCal/GPX export
│── sentinel.py         # DBSCAN clusters + velocity grading + Risk Pulse
│── advisory.py         # Travel Advisory brief — fusion engine + PDF / JSON / markdown
│── compass.py          # 🆕 Destination Showdown — multi-target ranking + JSON / markdown
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

**Compass score (destination showdown)**
```
compass = clip( safety_score − 16·forecast_risk_at_depart − cluster_penalty, 0, 100)
cluster_penalty = min(20, Σ_overlap status_weight · severity_mean/5)
   status_weight:  Critical 12 · Emerging 6 · Steady 2 · Cooling 0
```

---

## 📍 Roadmap

- [x] Real safety intelligence engine + heatmap + dark UI (round 1)
- [x] Risk-aware A\* router + dual-route UI (round 2)
- [x] AI-powered hazard forecasting (round 3 opener)
- [x] **Live Trip Companion + trusted-contacts broadcast** (round 3 closer)
- [x] **Multi-stop itinerary chaining** (2-opt order + Gantt + iCal export, Day 21)
- [x] **Sentinel — live cluster intel + emerging-hotspot alerts** (DBSCAN + velocity grading + Risk Pulse, Day 26)
- [x] **Travel Advisory — single-page pre-trip brief** (fusion engine + PDF / JSON / markdown, Day 31)
- [x] **Compass — multi-destination safety showdown** (depart-time ranking + heat-mapped matrix, Day 36)
- [ ] Real-time push (web-sockets) instead of file-tail simulation
- [ ] Mobile-first PWA shell with native geolocation feed
- [ ] Live traffic / road-closure overlay (HERE or Mapbox)

---

## 👨‍💻 Author

Built with ❤️ by **Aryan D Haritsa** — Student @ PES University · Entrepreneur ·
AI · Full-stack · research.
