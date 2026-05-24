# Credicrew

Credicrew is a talent-discovery tool that doesn't stop at "here's a ranked
list." It runs the **whole hiring loop**: parse a JD, get an explainable
shortlist, track candidates through statuses, send a tailored outreach
email, **run the interview** with a JD-tailored prep kit and a weighted
scorecard, **decide** in a calibrated comparison studio that ranks the
entire pool, **close** in an Offer Studio that benchmarks comp against
the market, simulates the candidate's accept-probability live, and ships
a print-ready offer letter, **audits the offer for fairness** against the
team's accepted peer offers so a one-week sprint doesn't quietly torch six
months of pay-band discipline — and now rolls every role up into a
**Command Center** so a recruiter running ten reqs sees the whole portfolio
on one screen. All from a dark, fast, single-page workspace.

The same scoring + email + interview + decision + offer logic runs in
the browser (for instant UI feedback) and on the FastAPI backend (for
programmatic / agentic use), so plans, drafts, composite scores, ranked
verdicts, and comp benchmarks are byte-for-byte identical wherever
they're generated.

---

## What's new — Command Center (Day 32)

Every other surface in Credicrew is single-role / single-candidate: open a
role, work one shortlist, score one interview, draft one offer. A recruiter
running ten reqs at once had no bird's-eye view. **Command Center** (`/hq`)
is the missing portfolio layer — every role, one screen.

- **Portfolio health score** — a single 0–100 number per role and across
  the book. It's a renormalised weighted blend of *momentum* (fresh vs
  stale candidates, 0.30), *interview coverage* (interviewed / reached
  interview, 0.25), *decision quality* (mean hire-signal, 0.25), and
  *offer confidence* (mean accept-probability, 0.20). Absent signals drop
  out and the remaining weights renormalise — same philosophy as the
  interview rubric — so a role with no offers yet isn't unfairly punished.
  The portfolio number weights each role by its active-candidate count.
- **Aggregate funnel** — `new → outreach → screening → interview → offer`
  rolled across all roles, with reached-at-least bars and adjacent-stage
  conversion rates colour-graded ≥50% emerald / 25–50% amber / <25% rose.
- **Comp-spend forecast** — sums year-1 total cash (`base + sign-on +
  base·bonus%`, mirroring the peer-parity definition) across every drafted
  offer. Shows **committed** (if every offer signs) vs **expected**
  (risk-weighted by each offer's live accept-probability from the Offer
  Studio logistic), plus average base and average accept odds.
- **Role leaderboard** — every role as a row with its health ring, a
  proportional stage bar, top candidate by hire signal, days open, a
  *stale* badge, and a *stuck · <stage>* bottleneck chip. Sort by health,
  in-flight count, or days open. Each row deep-links to the role.
- **Cross-role talent leaderboard** — your eight strongest people across
  *all* roles, ranked by hire signal, each deep-linking straight to their
  scorecard. The "who should I be fighting hardest to close" view.
- **Attention feed** — a prioritised, deep-linked action list: stale
  candidates (≥14 days, high at ≥21), offers tracking <45% to accept,
  signal-≥75 candidates still parked in *new/outreach* (fast-track), roles
  with a shortlist but no interviews, and empty roles. Sorted high → low.
- **One-click brief** — Copy or download a Markdown portfolio brief
  (health, comp forecast, funnel, top talent, attention) for a standup or
  a weekly hiring review.
- **Backend mirror** — `POST /portfolio/summary` takes a flattened
  snapshot of every role + shortlist (each candidate carrying match score,
  interview composite, offer draft, accept-probability) and returns the
  identical rollup. Math is byte-for-byte parity with the TS engine —
  confirmed by running the same fixed input through both. Accepts
  `camelCase` and `snake_case` payloads.

---

## What's new — Peer Parity (Day 27)

Decision Studio computes a calibrated interview composite. Offer Studio
turns that composite into a comp package. Until Day 27 the gap between
them was a blind spot: nothing checked whether the proposed offer was
*consistent* with how the team had paid past hires at a similar bar.
Day 27 closes that gap with **Peer Parity** — a fairness audit that sits
under the Offer Studio dial and flags every dimension that drifts off
the team's own band.

- **Per-dimension regression** — fits `dim = a·composite + b` across the
  team's peer offers for five dimensions (base · equity · sign-on ·
  target-bonus · year-1 total cash), z-scores the proposed offer against
  the residual stddev (with a `5%·mean` floor so a homogeneous team
  isn't infinitely strict), and bands each dim `in_band` (|z|<1.5),
  `stretch` (1.5–3.0), or `severe` (≥3.0).
- **Rank-inversion check** — for any peer who scored higher on interview
  composite yet is paid less than the proposal, the engine flags an
  **inversion** with the composite gap and the total-cash gap %. Even
  with all dims in-band, a single inversion bumps the verdict to
  `inversion` — the worst classification — because that's the one that
  blows up six months later when comp data leaks across the team.
- **Verdict ladder** — `fair · within team band` → `stretch · drifts on
  one dim` → `drift · multiple dims out-of-band or one severe` →
  `inversion · leapfrogs higher-composite peer`. Hero pill is
  band-coloured; drift score = max(|z|) is reported alongside.
- **Composite vs base scatter** — SVG chart of every peer with the
  dashed regression line, a translucent ±1σ band, and the proposed
  offer as a glowing star at the proposed composite. Hover any dot for
  the peer's composite + base + total. Pure inline SVG; zero new
  chart deps.
- **Per-dim parity bars** — 5 horizontal bars (one per dim) showing the
  expected band `[expected−σ, expected+σ]` as a violet→sky gradient,
  the expected center as a tick, and the proposed value as a pulsing
  status-tinted dot. Reads "where am I relative to where I should
  be" at a glance.
- **One-click fix suggestions** — for the worst-drifting dim, the
  engine computes the smallest single-axis move that brings |z| back
  inside 1.5 and prints it ("Bring base salary down to ₹68 LPA
  (Δ −₹12 LPA) to land inside the ±1.5σ band."). For each inversion,
  it prints the total-cash cut needed to clear it. A **"Snap to peer
  band"** button on the inversion alert applies the largest cut
  directly to the base slider — the rest of the Offer Studio
  (dial, factor bars, band ladder, letter) re-renders live off the
  parity move.
- **Per-role peer pool** — peers are scoped to the role's `id` in
  localStorage (`credicrew:peers:v1`) so deletions in one role don't
  leak across. First open auto-seeds the pool with 8 realistic
  India-engineering offers (Bengaluru/Mumbai/Pune, junior → principal,
  composite 65–89, base ₹28–₹138 LPA, R² ≈ 0.87) so the audit lights
  up immediately on a fresh install. A **Publish to peer pool** button
  snapshots the current proposal into the pool as a future peer.
  A right-side **Manage peers** drawer lists / adds / removes peers
  with a 10-field form (name · role · seniority · location ·
  composite · base · equity · sign-on · bonus · accepted-on).
- **Backend mirror** — `POST /peer-parity/check` (audit a proposal
  with caller-supplied peers — both `camelCase` and `snake_case`
  payloads accepted), `GET/POST/DELETE /peer-parity/peers?team=ID`
  (in-memory team pool CRUD, thread-safe via `RLock`), and
  `POST /peer-parity/check_team?team=ID` (audit using the pooled
  peers). Math is byte-identical to the TS engine — same regression
  closed form, same z thresholds, same suggestion strings.
- **Theme polish** — `.cc-parity-*` family in `globals.css`: hue-driven
  CSS custom property `--parity-hue` per verdict, a top accent rail
  drawn via `linear-gradient` + `color-mix(in srgb, …)`, a pulsing
  ring on the inversion-alert card, a drift-marker `cc-parity-pulse`
  animation that breathes the proposed dot inside each dim bar, and a
  drawer slide-in via `cc-parity-slide`.

---

## What's new — Offer Studio (Day 22)

Decision Studio picked the candidate. Offer Studio gets them to sign.
Day 22 closes the JD → match → outreach → interview → decision → **offer**
loop with the missing money + math layer.

- **Deterministic compensation benchmark** — P25 / P50 / P75 / P90 base
  bands derived from a Bengaluru-normalised seniority anchor, a city
  multiplier (Mumbai 1.05× · Bengaluru 1.00× · Pune 0.92× · Kochi
  0.78× …), and a skill-rarity premium (Kubernetes / Rust / PyTorch /
  Kafka / LLM bump +4% each; modern-stack signals — TS / FastAPI /
  Next.js / Postgres … — bump +1.5% each, capped at +20%). Equity
  bands by seniority (intern 0% · senior 0.10–0.30% · staff 0.25–0.65%
  · principal 0.50–1.40% …), target bonus %, and a suggested sign-on
  that auto-fills 50% of the P50→P75 gap.
- **Win-probability simulator** — explainable logistic model. Logit is
  a sum of weighted terms — `+3.5·(base/P50 − 1) + 0.8·(equity/P50 − 1)
  + 1.8·(signOn/base) − 0.18·rareSkills − 0.45·topTier − 0.2·decay
  − 0.5·thinData …` — and the UI renders every contribution as a
  signed bar so you can see *why* the number moves when you drag a
  slider. σ(logit) → probability, banded `long_shot / uphill /
  coin_flip / likely / lock`.
- **Live counterfactual sliders** — drag base, equity %, sign-on, target
  bonus %, vesting years, cliff. Comp ladder marker snaps to its band
  position; dial recomputes; factor stack re-orders by magnitude.
- **Print-ready offer letter** — Markdown composer renders a clean
  letter (company, role, location, table of comp items, vesting, band
  position commentary, notes, sign-off) into an in-app preview;
  `Print / PDF` button uses a dedicated `@media print` stylesheet to
  swap to light-on-white. `Download .md` ships the Markdown.
- **iCal offer-expiry event** — generates an RFC-5545 `.ics` for the
  offer-expiry date with all the comp lines folded into the
  DESCRIPTION, so your calendar reminds you (and your candidate) before
  it lapses.
- **Auto-save drafts** — every slider tweak persists to localStorage
  under `credicrew:offers:v1`, keyed `${roleId}:${candidateId}`, so you
  can flip between candidates without losing state.
- **Backend mirror** — 4 new endpoints on the FastAPI app, all
  parity-tested against the TS engine. `POST /offer/benchmark` (band +
  equity + sign-on + bonus from JD/plan + matched skills),
  `POST /offer/simulate` (win-prob + per-factor logit contributions for
  a draft), `POST /offer/compose` (Markdown letter), and
  `POST /offer/full` (one-shot bundle for agentic clients). Pydantic
  accepts both snake_case and camelCase so curl-driven and TS clients
  hit the same endpoints.
- **Deep links** — Decision Studio focus pane gained `Offer Studio →`
  (gradient emerald→violet). Role-detail shortlist rows gained a
  per-row `Offer →` button next to *Start interview*.

---

## What's new — Decision Studio (Day 17)

The interview kit produced a per-candidate scorecard but stopped there.
Day 17 adds the missing **decision layer**: side-by-side calibration,
ranked verdicts, and one-click iCal scheduling.

- **Calibrated comparison matrix** — All shortlisted candidates as
  columns × rubric dimensions as rows. Cells are heat-mapped 1–5 (rose →
  amber → indigo → emerald), with a ★ marker on the top scorer per dim.
  Click a dim label to sort the matrix by it; click a column header to
  inspect that candidate; click ☆ to pin candidates and toggle a
  pinned-only view for head-to-head comparison.
- **Hire signal** — Composite × √(confidence). A 100-composite candidate
  with only 40% of dims rated lands at signal ≈ 63 — *still ranked*, but
  visibly behind a fully-rated 80-composite peer at signal 80. Sqrt
  blunts the penalty so partial coverage doesn't completely tank a strong
  candidate. Tier histogram across the pool sits above the matrix.
- **Risk flags per candidate** — `thin_data`, `low_confidence`,
  `missing_key_dim` (top-3 weighted dim has no rating), `high_variance`
  (stdev across rated dims ≥ 1.5), `rubric_drift` (a dim was rated in one
  done stage but not in another), `no_interview`, `unrated`.
- **Hiring committee debrief** — One-click Markdown export with the
  ranked verdict list, per-candidate strengths/concerns/flags, recommended
  hire callout, recommendation tally, next-round candidates, and
  per-rubric mean/spread/coverage.
- **iCal slot proposer** — RFC-5545-compliant `.ics` generator. Auto-fills
  the next 5 weekday business slots (10:00 / 14:00 / 16:00 local), pick
  any subset, fills `SUMMARY` / `DESCRIPTION` / `LOCATION` / organiser /
  attendee, then downloads a single `VCALENDAR` with N `VEVENT`s.
  CRLF-terminated, UTC `Z`-suffixed, `,;\n\\` escaped, line-folded at 75
  octets. Drops cleanly into Gmail, Outlook, Apple Calendar.
- **Pipeline analytics** — Reached-at-least funnel + adjacent-stage
  conversion rates (≥50% emerald, 25-50% amber, <25% rose), status mix
  bar, stale-candidate watchlist (≥14 days in non-terminal status).
- **Backend mirror** — `POST /decision/summary` (calibrated ranking
  + verdicts + per-dim stats + counts + optional debrief),
  `POST /decision/debrief` (Markdown only), `POST /interview/ics`
  (returns `text/calendar` with a `Content-Disposition: attachment`
  filename header). Same engine, same numbers — agentic clients get
  byte-identical verdicts.

---

## What's new — Interview Kit (Day 12)

The hiring loop ended at *outreach* — when a candidate flipped to
`interview` status, the app went silent. Day 12 fills that gap with a
deterministic, JD-tailored Interview Kit.

- **Tailored question bank** — From the parsed JD plan, the engine picks
  prompts out of a 13-skill bank (React, Next.js, TypeScript, FastAPI,
  Python, Postgres, MongoDB, Redis, AWS, Docker, Kubernetes, PyTorch, LLM)
  and slots each into the natural stage (technical / system design),
  alongside a universal phone-screen / behavioral set. A typical
  back-end JD produces ~18 prompts across 4 stages.
- **Weighted rubric** — 4–7 dimensions: skill-driven dims (Frontend depth,
  Backend depth, Data systems, Cloud / infra, ML systems, Language craft)
  collapse duplicate skills (`react` + `next.js` both feed *Frontend
  depth*), with Σ-weight bumped per duplicate skill. Universal dims —
  *Communication · Ownership · Collaboration · System design* — round it
  out, plus a *Scope & influence* bonus dim for senior+ roles. Weights
  renormalise so they always sum to 1.
- **Composite + recommendation** — `Σ ((rating−1)/4) · weight · 100` over
  rated dims (weights renormalise across rated dims so a half-finished
  scorecard still produces a meaningful number). Bands: ≥80 strong-hire ·
  ≥65 lean-yes · ≥50 mixed · ≥35 lean-no · else no-hire.
- **Workspace UI** — `/roles/[id]/interview/[candidateId]`. Stage stepper
  with per-stage rated/total counts; expandable question cards with
  difficulty + signal pills + collapsible follow-ups; per-stage rubric
  sliders coloured by rating; per-stage signal log (strengths / concerns)
  with quick-add; live recommendation ring + composite breakdown bar
  chart; Markdown report export.
- **Role-detail integration** — every shortlist row now shows an
  `iv · <composite>` chip in the candidate's recommendation tone the
  moment any rating is filled in, plus an *Open / Start interview* button
  that drops into the workspace. A new **Export CSV** action ships the
  whole shortlist (incl. interview composite + recommendation) for ATS
  handoff — closing another roadmap item.

---

## What's new — Recruiter Workspace

Day 7 of the rotation moved Credicrew from "ranking page" to "hiring loop."

- **Roles** — Save a JD as a Role with its own parsed plan and shortlist.
  Edit the JD, rename the role, browse fresh matches, and add candidates
  with one click. Each role lives in your browser via localStorage.
- **Pipeline statuses** — Every shortlisted candidate moves through
  `New → Outreach → Screening → Interview → Offer / Passed` via a per-row
  status select. Per-status counts and a coloured pipeline strip show
  the funnel at a glance.
- **Outreach composer** — A deterministic email generator (no LLM call)
  that pulls in the candidate's first name, the matched skills, the JD's
  pitch line, the score, and the location stance. Edit, copy subject /
  body / both, or hand off to your mail client via `mailto:`.
- **Diversity widget** — Live composition view of the current pool:
  city donut (top 5 + "Other"), seniority bars, top skill frequencies.
  Renders both on Discover and inside each Role.
- **Shareable role links** — `Share link` on a role copies a URL that
  encodes the role name, JD, and shortlist into the URL hash. Recipients
  can preview before saving to their own workspace.

---

## Features

### Explainable matching
- Free-text query parsing: extracts **skills**, **location**, and **seniority**
  from natural prose (`"Senior backend (FastAPI + Postgres) in Bengaluru"` →
  skills `fastapi, postgres`, location `bengaluru`, seniority `senior`).
- Alias normalization: `reactjs → react`, `nodejs → node.js`,
  `bangalore → bengaluru`, `k8s → kubernetes`, etc.
- Per-candidate breakdown: matched skills, missing skills, location state
  (`full` / `partial` / `none`), seniority match.
- Score bands: **strong** (≥80), **solid** (≥60), **weak** otherwise — shown
  as coloured dot counts in the results header and as a conic-gradient ring
  on each card.

### Scoring formula
Composite score in `[0, 1]`, scaled to 0–100:

| Factor      | Weight | What it measures                                  |
|-------------|-------:|---------------------------------------------------|
| Skills      | 0.55   | Fraction of requested skills the candidate has    |
| Seniority   | 0.20   | Exact match (1.0), known-but-different (0.3), unknown (0.6) |
| Location    | 0.15   | Exact / remote (1.0), hybrid (0.5), mismatch (0.0)|
| Baseline    | 0.10   | Flat floor so a blank query still ranks sensibly  |

### Roles & pipeline
- `/roles` — list of saved roles with a per-role pipeline strip and chips
  for the parsed plan.
- `/roles/new` — paste a JD, sample loader for a quick demo, live plan
  detection.
- `/roles/[id]` — JD editor, plan chips, **Matches** tab with the
  Diversity widget, **Shortlist** tab with status select + private notes,
  delete, share.
- `/roles/share` — preview and import a role from a `data=…` hash token.

### Outreach
- `composeEmail({ role, candidate, match })` produces `{ subject, body }`.
- Subject highlights the top matched skill when available.
- Body addresses the candidate by first name, names the matched skills,
  threads in the JD pitch line, addresses the location stance, and
  optionally cites the explainable score.
- Modal is editable and offers copy-to-clipboard for subject / body / both
  plus an `Open in mail app` mailto link.

### Discover (existing)
- Detected-plan chips show exactly which tokens the parser picked up.
- Min-score slider filters the deck live.
- "Save as role" button captures the current query as a Role.
- Each `CandidateCard` ring's colour matches the score band; matched
  skills are emerald chips, missing skills are rose strike-throughs.
- `MatchExplain` popover lists every factor's contribution in points.
- Per-card **Shortlist** picker drops a candidate into any saved role.

---

## Tech stack
- **Frontend:** Next.js 14 (App Router) · TypeScript · TailwindCSS
- **Backend:** FastAPI · Pydantic v2 · SQLAlchemy 2.0
- **Match + outreach engines:** pure functions, no external NLP / LLM deps —
  kept in lockstep between
  `frontend/src/lib/{match,outreach}.ts` and
  `backend/app/services/{match,outreach}.py`.

---

## Getting started

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://127.0.0.1:8000

# Frontend (new shell)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

---

## API

### `POST /match`
Rank an arbitrary list of candidates against a natural-language query.

```bash
curl -X POST http://127.0.0.1:8000/match \
  -H 'content-type: application/json' \
  -d '{
    "query": "Senior backend (FastAPI + Postgres) in Bengaluru",
    "candidates": [
      {"id": 1, "name": "A Patel", "role": "Senior Backend Engineer",
       "location": "Bengaluru", "tags": ["fastapi","postgres"], "keywords": []},
      {"id": 2, "name": "B Kumar", "role": "Frontend Engineer",
       "location": "Remote (India)", "tags": ["react","typescript"], "keywords": []}
    ]
  }'
```

### `POST /outreach`
Compose a personalized outreach email. Either pass a `jd` (parsed
server-side) or pre-parsed `plan_*` fields.

```bash
curl -X POST http://127.0.0.1:8000/outreach \
  -H 'content-type: application/json' \
  -d '{
    "role_name": "Senior Backend Engineer",
    "jd": "Senior Backend Engineer (FastAPI + Postgres) in Bengaluru. Real-time risk engine.",
    "candidate": {
      "id": 1, "name": "A Patel", "role": "Senior Backend Engineer",
      "location": "Bengaluru", "tags": ["fastapi","postgres"]
    },
    "sender": "— Aryan, Founding Recruiter"
  }'
```

Response:
```json
{
  "subject": "Quick chat about a Senior Backend Engineer role — your fastapi work caught my eye",
  "body": "Hi A,\n\nI'm reaching out about a Senior Backend Engineer opportunity — …",
  "context": {
    "role_name": "Senior Backend Engineer",
    "matched_skills": ["fastapi", "postgres"],
    "score": 100,
    "plan": {"skills": ["fastapi","postgres"], "location": "bengaluru", "seniority": "senior"}
  }
}
```

### `POST /interview/plan`
Generate a tailored interview plan (rubric + question bank + empty stage
records) from a JD or pre-parsed plan.

```bash
curl -X POST http://127.0.0.1:8000/interview/plan \
  -H 'content-type: application/json' \
  -d '{"jd": "Senior backend engineer (FastAPI + Postgres) in Bengaluru"}'
```

Returns `{ rubric: [...], questions: [...], stages: [...] }`. Rubric
weights always sum to 1.

### `POST /interview/score`
Aggregate a filled-in scorecard to a composite + recommendation.

```bash
curl -X POST http://127.0.0.1:8000/interview/score \
  -H 'content-type: application/json' \
  -d '{
    "rubric": [{"key":"backend_depth","label":"Backend depth","description":"","weight":0.25,"source":"skill"},
               {"key":"data_systems","label":"Data systems","description":"","weight":0.25,"source":"skill"},
               {"key":"system_design_skill","label":"System design","description":"","weight":0.25,"source":"skill"},
               {"key":"communication","label":"Communication","description":"","weight":0.25,"source":"communication"}],
    "stages": [{"stage":"technical","status":"done","scores":[{"key":"backend_depth","rating":4},{"key":"data_systems","rating":4}]},
               {"stage":"behavioral","status":"done","scores":[{"key":"communication","rating":5}]}]
  }'
```

Returns `{ composite, recommendation, rated_count, total_count, per_dimension }`.

### `POST /decision/summary`
Calibrated ranking across a role's interviewed pool. Pass each candidate's
parsed plan or JD plus their interview record (rubric + filled stages).
Returns ranked `verdicts[]` with `hire_signal = round(composite ·
√confidence)`, per-candidate flags, per-dim stats (mean / coverage /
spread / best scorer), recommendation counts, and the top-hire id. Set
`include_debrief: true` to bundle the committee Markdown.

### `POST /decision/debrief`
Same input shape as `/decision/summary`, returns `{ markdown }` only —
useful when the client already has the summary cached.

### `POST /interview/ics`
Build an iCalendar `VCALENDAR` with N `VEVENT`s and stream it as
`text/calendar; charset=utf-8` with a `Content-Disposition: attachment`
header. CRLF-terminated, UTC `Z`-suffixed `DTSTART`/`DTEND`, line-folded
at 75 octets, `\,;\n\\` escaped per RFC 5545 §3.3.11.

### `POST /offer/benchmark`
Compensation benchmark from a JD (or pre-parsed plan) + the candidate's
matched skill list. Returns `{ benchmark: { base: {p25,p50,p75,p90}, equity:
{pct_p25,pct_p50,pct_p75}, targetBonusPct, signOnSuggested, citymult,
skillPremium, rationale }, suggested?: OfferDraft }`.

```bash
curl -X POST http://127.0.0.1:8000/offer/benchmark \
  -H 'content-type: application/json' \
  -d '{
    "jd": "Senior backend engineer (FastAPI + Postgres + Kubernetes) in Bengaluru",
    "matched_skills": ["fastapi","postgres","kubernetes"]
  }'
```

### `POST /offer/simulate`
Runs the win-probability logistic for a given draft + benchmark.
Returns `{ benchmark, win: { probability, logit, band, factors[] }, bandPosition }`
where each `factor` carries a `delta` (its contribution to the logit) so the
caller can render the explanation. Accepts both snake_case and camelCase
draft fields (`equity_pct` ≡ `equityPct`, `sign_on` ≡ `signOn`, …).

### `POST /offer/compose`
Renders the Markdown offer letter. Returns `{ markdown, benchmark }`.

### `POST /offer/full`
Convenience bundle — runs `benchmark + simulate + compose` in one
round-trip. Used by agentic clients that don't want three sequential calls.

### `POST /peer-parity/check`
Fairness audit. Accepts a proposed offer (composite + base + equity %
+ sign-on + target-bonus %) and a list of peer offers, returns the
parity verdict, per-dim z-scores, the regression coefficients
(`a · b · r² · σ · n`), the ranked inversion list, the 5 nearest peers
by composite, the SVG-ready scatter array, and one-line suggestions.
Both `camelCase` and `snake_case` payloads accepted via Pydantic
aliases.

### `POST /portfolio/summary`
Portfolio rollup across every role. Accepts `{ roles: [...], now? }` where
each role carries its shortlist and each candidate carries `matchScore`,
`composite`, `confidence`, `recommendation`, an optional `offer` draft, and
an optional `winProbability`. Returns `{ totals, funnel, compForecast,
roleHealth, talent, attention, recommendationMix, portfolioHealth,
bottleneck }`. Both `camelCase` and `snake_case` payloads accepted.

```bash
curl -X POST http://127.0.0.1:8000/portfolio/summary \
  -H 'content-type: application/json' \
  -d '{
    "roles": [{
      "id": "r1", "name": "Senior Backend", "seniority": "senior",
      "candidates": [
        {"candidateId": 1, "name": "Asha", "status": "offer",
         "matchScore": 88, "composite": 82, "confidence": 1.0,
         "recommendation": "strong_hire",
         "offer": {"base": 52, "equityPct": 0.18, "targetBonusPct": 12, "signOn": 6},
         "winProbability": 0.7}
      ]
    }]
  }'
```

### `POST /peer-parity/check_team?team=ID`
Same response shape but pulls peers from the in-memory team pool
keyed by `team` (defaults to `"default"`). Useful when an agentic
client has already curated a team pool and just wants the audit.

### `GET/POST/DELETE /peer-parity/peers?team=ID`
Team pool CRUD. `GET` returns `{ team, peers, count }`. `POST` accepts
a `PeerIn` body and upserts by `id`. `DELETE /peer-parity/peers/{id}`
returns 404 if the id wasn't in the pool. Thread-safe via `RLock`.

### Endpoint map

| Method | Path                          | Purpose                                                 |
|-------:|-------------------------------|---------------------------------------------------------|
| GET    | `/health`                     | liveness                                                |
| GET    | `/candidates`                 | demo candidate listing                                  |
| GET    | `/roles`                      | demo role listing                                       |
| POST   | `/match`                      | rank candidates against a query (explainable)           |
| POST   | `/outreach`                   | compose deterministic outreach email                    |
| POST   | `/interview/plan`             | tailored rubric + question bank from JD / plan          |
| POST   | `/interview/score`            | aggregate scorecard → composite + recommendation        |
| POST   | `/interview/ics`              | RFC-5545 `.ics` for proposed interview slots            |
| POST   | `/decision/summary`           | calibrated ranking + verdicts + per-dim stats           |
| POST   | `/decision/debrief`           | Markdown committee debrief                              |
| POST   | `/offer/benchmark`            | comp + equity + sign-on benchmark (P25/P50/P75/P90)     |
| POST   | `/offer/simulate`             | win-probability + per-factor logit contributions        |
| POST   | `/offer/compose`              | Markdown offer letter                                   |
| POST   | `/offer/full`                 | benchmark + simulate + compose bundle                   |
| POST   | `/peer-parity/check`          | audit a proposal against caller-supplied peers          |
| POST   | `/peer-parity/check_team`     | audit a proposal against the in-memory team pool        |
| GET    | `/peer-parity/peers`          | list peers in the team pool                             |
| POST   | `/peer-parity/peers`          | add / upsert a peer in the team pool                    |
| DELETE | `/peer-parity/peers/{id}`     | remove a peer from the team pool                        |
| POST   | `/portfolio/summary`          | portfolio rollup across every role (Command Center)     |

---

## Project structure

```
Credicrew/
├── backend/
│   └── app/
│       ├── main.py                 # FastAPI + CORS + routers
│       ├── routers/
│       │   ├── match.py            # POST /match
│       │   ├── outreach.py         # POST /outreach
│       │   ├── interview.py        # POST /interview/{plan,score}
│       │   ├── decision.py         # POST /decision/{summary,debrief}
│       │   ├── offer.py            # POST /offer/{benchmark,simulate,compose,full}
│       │   ├── peer_parity.py      # POST /peer-parity/{check,check_team} + peers CRUD
│       │   └── portfolio.py        # POST /portfolio/summary
│       └── services/
│           ├── match.py            # explainable engine
│           ├── outreach.py         # email composer
│           ├── interview.py        # rubric · question bank · scorecard
│           ├── decision.py         # calibrated ranking + verdicts
│           ├── offer.py            # comp band · win-prob · letter
│           ├── peer_parity.py      # regression · z-scores · inversions · suggestions
│           └── portfolio.py        # portfolio rollup · funnel · comp forecast · health
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx            # Discover (search + composition + roles)
│       │   ├── hq/page.tsx         # Command Center (portfolio rollup)
│       │   ├── pipeline/page.tsx   # Quick-saves
│       │   └── roles/
│       │       ├── page.tsx        # Roles list
│       │       ├── new/page.tsx    # New role from JD
│       │       ├── share/page.tsx  # Import a shared role
│       │       └── [id]/
│       │           ├── page.tsx    # Role detail (JD, matches, shortlist, CSV)
│       │           ├── decision/page.tsx                 # Decision Studio
│       │           ├── interview/[candidateId]/page.tsx  # Interview workspace
│       │           └── offer/[candidateId]/page.tsx      # Offer Studio (NEW)
│       ├── components/
│       │   ├── CandidateCard.tsx
│       │   ├── CompLadder.tsx           # P25→P90 comp band with offer marker
│       │   ├── DecisionMatrix.tsx       # rubric × candidate heatmap
│       │   ├── DiversityCard.tsx
│       │   ├── InterviewStepper.tsx
│       │   ├── MatchExplain.tsx
│       │   ├── OfferLetterPreview.tsx   # print-ready offer letter renderer
│       │   ├── OutreachModal.tsx
│       │   ├── PeerParityPanel.tsx      # SVG scatter + per-dim bars + suggestions
│       │   ├── PeerPoolDrawer.tsx       # right-side drawer for peer CRUD
│       │   ├── PipelineAnalytics.tsx    # funnel + conversion rates
│       │   ├── QuestionCard.tsx
│       │   ├── RecommendationRing.tsx
│       │   ├── RoleCard.tsx
│       │   ├── RubricSlider.tsx
│       │   ├── SlotProposer.tsx         # iCal slot picker
│       │   ├── StatusPill.tsx
│       │   └── WinProbabilityDial.tsx   # SVG dial + signed factor bars
│       └── lib/
│           ├── csv.ts              # tiny RFC-4180 writer + downloader
│           ├── decision.ts         # calibrated ranking · flags · debrief
│           ├── ics.ts              # RFC-5545 minimal generator
│           ├── interview.ts        # rubric · question bank · scorecard
│           ├── match.ts            # TS match engine (parity w/ backend)
│           ├── offer.ts            # comp band · win-prob · letter (parity w/ backend)
│           ├── outreach.ts         # TS email composer (parity w/ backend)
│           ├── peer_parity.ts      # regression · z-scores · inversions (parity w/ backend)
│           ├── peer_seed.ts        # 8-peer realistic seed for fresh roles
│           ├── portfolio.ts        # portfolio rollup · funnel · comp forecast · health
│           ├── pipeline.ts         # quick-save ids
│           └── roles.ts            # roles + shortlist + share-link state
└── docs/
```

---

## Roadmap
- Server-persisted roles (Postgres) so they survive across browsers.
- LLM-assisted JD parsing for messy real-world specs (still fall back to
  the deterministic path).
- ~~Per-role "team peer parity" check — flag offers that drift too far
  from the team's existing accepted offers at similar interview composite.~~ ✅ Day 27.
- ~~iCal export for an "Interview" status with proposed slots.~~ ✅ Day 17.
- ~~CSV export of a shortlist for ATS handoff.~~ ✅ Day 12.
- ~~Interview kit: tailored prompts, weighted rubric, scorecard, hire/no-hire signal.~~ ✅ Day 12.
- ~~Decision Studio: calibrated comparison, hire signal, committee debrief.~~ ✅ Day 17.
- ~~Offer Studio: comp benchmarking, accept-probability simulator, print-ready letter.~~ ✅ Day 22.

---

## License
MIT © 2025 Credicrew
