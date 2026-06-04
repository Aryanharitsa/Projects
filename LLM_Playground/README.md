# 🧪 LLM Playground

A side‑by‑side LLM evaluation studio. Run the **same prompt** against multiple
frontier models in parallel, score them with an LLM‑as‑judge (or a **panel of
judges**), **vote on them yourself**, version your prompts, keep **every run**
in a queryable, comparable history, see the **quality/cost frontier** across
your whole spend in Insights, define **Eval Suites** to catch regressions
before users do, and — new this round — build **Rubrics**: first‑class,
anchor‑driven, versioned judge sheets you can save, share, test, and reuse
across every other surface.

Built with a Flask backend and a React + Tailwind + shadcn/ui frontend.

---

## 🆕 What's new — Rubrics Studio (anchor‑driven, versioned judge sheets)

> Round‑9. Every surface in the playground that scores something has been
> using the same generic "score this 1‑5" rubric since day one. That works
> for casual A/B, but a real evaluation workflow needs **domain rubrics** —
> "Groundedness" for RAG, "Tone safety" for support, "Edge cases" for
> code — each with its own anchor descriptions for what a 0/5/10 looks
> like. This move ships the studio that builds them.

Hit **Rubrics** in the sidebar. A rubric is a named, reusable scoring sheet:

- **Dimensions** — each dimension has a `name`, a one‑line `description`, an
  integer `weight` (sliders that normalise to 100 on save), and a 0/5/10
  **anchor block** explaining what each score level looks like for *this*
  dimension.
- **Judge guidance** — an optional addendum the judge model sees alongside the
  dimensions ("treat unsupported claims as the most severe failure mode" /
  "penalise generic AI‑flavoured prose").
- **Server‑computed composite** — the judge returns per‑dimension scores
  (0‑10) and rationales; the backend computes the 0‑100 composite from the
  rubric weights so a misbehaving judge can't poison the math.
- **Versioning** — every dimension/anchor/addendum edit appends a new
  `rubric_revision` (append‑only, just like `prompt_versions`). The current
  revision pointer always moves forward; you can restore an older revision
  with a single click — a restore is itself a new revision so the history
  is honest.
- **One‑click test** — paste a `(prompt, response)` pair, pick a judge
  provider/model, hit *Run rubric judge*. You get a score ring, per‑dimension
  progress bars, per‑dimension rationale, the judge's verdict line, latency
  and cost. Each test is logged so the global stats stay live.
- **Stats** that mean something — total rubrics, total judgements, average
  composite across all rubrics, total judge spend, the **best candidate
  model** across all rubric tests (min 3 judgements), and the **top judges**
  by usage with their average latency + spend.

### Seed → in 10 seconds

First‑click **Seed 4 starter rubrics**:

1. **Code Review** — 40% correctness, 20% idiomatic, 20% edge cases, 20%
   readability. Each dimension has anchors like "*Doesn't compile / runs but
   produces wrong output / hallucinated APIs*" at the 0 mark.
2. **RAG Faithfulness** — 40% groundedness, 25% relevance, 20% citation, 15%
   calibration. Treats any confidently stated unsupported claim as the most
   severe failure (anchor 0 = "*Multiple confident claims absent from the
   context*").
3. **Customer Support** — 30% tone, 30% resolution, 25% accuracy, 15%
   brevity. Anchors explicitly call out blame‑the‑customer and missing
   next‑step failure modes.
4. **Creative Writing** — 30% voice, 25% imagery, 25% structure, 20%
   restraint. Anchors penalise generic AI‑flavoured prose and reward earned
   structural choices.

### Why anchors + per‑dim rationale matter

The judge prompt is generated from the rubric: every dimension's `weight`,
`description`, *and* its 0/5/10 anchors get serialised into the body
verbatim. The judge then returns:

```json
{
  "scores":     { "Groundedness": 8, "Relevance": 9, "Citation": 6, "Calibration": 7 },
  "rationales": { "Groundedness": "claim about CVE-2024-1234 isn't in the context",
                  "Relevance":    "answers the asked question precisely",
                  "Citation":     "cites the right passage but format is loose",
                  "Calibration":  "appropriately hedges where context is silent" },
  "summary":    "Solid faithful answer with one citation hygiene issue."
}
```

The composite (0‑100) is computed *server‑side* from `scores × weights`, so
the judge can't fabricate it. The UI renders a score ring, per‑dimension
progress bars colour‑coded by score, and each dim's `contributes N pts to
composite` so the *why* is visible.

### Why every edit is a revision

Pass/fail history is only meaningful if you can answer "did this rubric
change between these two runs?". `update_rubric` computes a deterministic
signature over the dimensions+addendum: identical → no new revision;
different → append‑only insert and the rubric's `current_revision_num`
moves forward. A restore copies an older revision forward as a new
revision (so r1 → r4 = "we restored r1"), and the revision list shows
notes, parent links, dim counts, and a single‑click *Restore* per row.

### API surface

```
POST   /api/rubrics                                  create
GET    /api/rubrics                                  list (q, tag, starred, limit, offset)
POST   /api/rubrics/seed                             idempotent — 4 starter rubrics
GET    /api/rubrics/stats                            portfolio rollup
GET    /api/rubrics/:id                              read (current rev + history + recent judgements)
DELETE /api/rubrics/:id                              cascade delete
POST   /api/rubrics/:id/meta                         {name?, description?, tag?, starred?}
POST   /api/rubrics/:id/revisions                    save a new revision iff dims changed
POST   /api/rubrics/:id/revisions/:n/restore         copy revision n forward as current
POST   /api/rubrics/:id/test                         judge an ad‑hoc (prompt, response) pair
GET    /api/rubrics/:id/judgements                   judgement log for this rubric
DELETE /api/rubrics/judgements/:jid                  drop one logged judgement
```

### Schema

Three tables share the same `history.db` so a single backup captures
everything:

| table                | purpose                                         |
|----------------------|-------------------------------------------------|
| `rubrics`            | one row per rubric — name, tag, star, head ptr  |
| `rubric_revisions`   | append‑only chain of `(dimensions_json, addendum, note, parent_revision)` |
| `rubric_judgements`  | every test logged — prompt, response, per‑dim scores, judge model, latency, cost |

Indexed on `updated_at DESC`, `starred`, `(rubric_id, revision_num DESC)`,
`(rubric_id, created_at DESC)`, `(candidate_provider, candidate_model)` so
the UI list, the revision drawer, the judgement log, and the "best model"
roll‑up all stay snappy under thousands of rows without paying SQLite‑JSON1
indexing tax.

### Engine highlights

- `_normalise_dimensions` validates names + clamps weights, then re‑packs
  weights to **integer percents summing to exactly 100** using the
  largest‑remainder method — the UI sees clean integers and the composite
  math is deterministic.
- `build_rubric_judge_prompt` renders the rubric (name + weight + description
  + per‑level anchors), the user prompt, the optional system prompt, the
  addendum, the response, and a JSON output schema in one body — same
  paranoia as `judge.build_judge_prompt`.
- `parse_rubric_response` strips ```json fences, finds the first balanced
  `{...}` block, tolerates case‑insensitive dimension keys, **clamps every
  score to [0, 10]**, and falls back to zeros + a `(judge did not return a
  verdict)` rationale when parsing fails — `parsed_ok` flags the failure so
  the UI can warn instead of silently scoring 0.
- `_composite` computes `Σ (score_i / 10 × weight_i / 100) × 100` server‑side
  — the judge has no say.
- All DB writes go through a single non‑reentrant lock; the `update_rubric`
  no‑op path explicitly exits the lock before calling back into `get_rubric`
  to avoid the deadlock that catches every "we share a lock with our reader"
  refactor (asked me how I know).

### How this plugs into the rest of the studio

This round is purely the studio. The next move is the integration pass:

- **Eval Suites** will accept `rubric_id` in `run_suite` so a suite is
  judged with a named rubric instead of an inline JSON blob, and pass/fail
  becomes per‑dimension (not just composite ≥ N).
- **Arena / Judge / Consensus** will offer "score with rubric →" against
  any saved rubric, persisting the verdict to `rubric_judgements` so the
  global stats and the best‑model leaderboard always reflect every score
  the studio has ever produced.

---

## What's new in Round‑8 — Eval Suites (reproducible test batteries + regression detection)

> Round‑8. The playground had every *one‑off* measurement tool (Arena,
> Judge, Consensus, Vote, History, Library, Insights) but no way to run the
> **same fixed battery of cases** against every candidate model and watch
> for regressions when you change the prompt. That's what every real
> LLM‑ops workflow eventually needs — and that's what this move ships.

Hit **Suites** in the sidebar. A suite is a named, ordered list of *test
cases*. Each case is a user prompt plus zero or more pass criteria
(AND‑combined):

- **`must contain`** — case‑insensitive substring.
- **`must NOT contain`** — substring must be absent (catches refusals,
  hallucinated phrases, banned style).
- **`regex match`** — Python `re.search` over the response.
- **`valid JSON`** — response (with optional ```json fences stripped) must
  parse with `json.loads`.
- **`judge ≥ N`** — LLM‑as‑judge composite must clear a threshold; checked
  only when the run is judged.

A case with no criteria is a **latency‑only smoke** — pass = the call
succeeded with a non‑empty body.

### What you get for free

- **First‑click "Seed Smoke Test"** — six starter cases (factual recall,
  refusal, JSON formatting, arithmetic, summarisation quality, code
  synthesis) so a brand‑new user can press *Run* in 10 seconds and see
  every column populate.
- **The Run Config panel** — pick a provider/model, optionally turn on a
  judge model, and a single click fans the whole suite out in parallel
  (`ThreadPoolExecutor`, cap of 6 workers — a 12‑case suite finishes in
  ~2× the slowest call, not 12×).
- **The Run Report** — 4 gradient KPI tiles (pass rate, avg composite,
  total cost, wall time), a **criteria breakdown** that pivots every
  AND‑combined rule across cases ("`regex` passed 4/5, `judge_min` passed
  3/5"), and per‑case rows you can expand to see the prompt, the
  response, the judge rationale, and a **per‑criterion checklist** of why
  it passed or failed.
- **Run history per suite** with a **side‑by‑side compare drawer**: pick
  any two runs (different models, same model after a prompt edit, or the
  same model at different points in time), see the headline deltas
  (Δpass‑rate, Δcomposite, Δcost, Δwall‑time) and a **per‑case regression
  table** that calls out **fixed** vs **regressed** vs **same** with an
  icon. This is the screenshot you ship in PRs.
- **A global stats banner** at the top — total suites, cases, runs,
  spend, plus the **best model** crown (highest avg pass‑rate across all
  its runs, with run count next to it).

### Why every criterion has its own reason

Pass/fail isn't a black box. The engine returns a `reasons[]` array per
case — each entry is `{kind, expected, ok, detail?}` — so the UI can
render a per‑criterion chip‑row showing which rules fired green, which
fired red, and *why* (e.g. `judge_min: ≥70 · got 64.2`). When you fail a
case, you can see in two seconds whether it was the substring, the
regex, the JSON parse, or the judge.

### API surface

```
POST   /api/suites                       create suite
GET    /api/suites                       list (q, tag, starred, limit, offset)
POST   /api/suites/seed                  idempotent "Smoke Test" starter
GET    /api/suites/stats                 portfolio rollup + best model
GET    /api/suites/<id>                  detail + cases + recent_runs[]
POST   /api/suites/<id>/meta             rename / re‑tag / star
DELETE /api/suites/<id>                  cascade‑delete cases + runs + results
POST   /api/suites/<id>/cases            add case
POST   /api/suites/<id>/cases/<cid>      update case
DELETE /api/suites/<id>/cases/<cid>      delete + re‑pack indices
POST   /api/suites/<id>/cases/reorder    body: { case_ids: [...] }
POST   /api/suites/<id>/runs             kick off a run (sync, parallel)
GET    /api/suites/<id>/runs             list recent runs for this suite
GET    /api/suites/runs/<rid>            run report + per‑case results[]
DELETE /api/suites/runs/<rid>            delete a run + its results
POST   /api/suites/runs/compare          body: { a, b } → per‑case diff
```

### `POST /api/suites/<id>/runs` body

```json
{
  "provider":       "OpenAI",
  "model":          "gpt-4o",
  "system_prompt":  "optional, applied to every case",
  "judge_provider": "Anthropic",
  "judge_model":    "claude-3-5-sonnet-20241022",
  "rubric":         [{"name": "Correctness", "weight": 0.4, ...}],
  "note":           "after tightening the system prompt"
}
```

Response (`run`) includes `n_passed/n_failed/n_errored`, `pass_rate`,
`avg_composite`, `total_cost`, `wall_latency`, plus a `results[]` array
where every entry carries the response, latency, cost, judge composite +
rationale, the boolean `passed`, and the per‑criterion `reasons[]` so you
never have to ask "*why* did this fail?"

### `POST /api/suites/runs/compare` returns

```json
{
  "summary": {
    "a": { "id": "...", "model_key": "OpenAI:gpt-4o", "pass_rate": 83.3, "avg_composite": 71 },
    "b": { "id": "...", "model_key": "OpenAI:gpt-4o-mini", "pass_rate": 66.6, "avg_composite": 62 },
    "delta": { "pass_rate": -16.7, "avg_composite": -9, "total_cost": -0.0085, "wall_latency": -1.2 }
  },
  "rows": [
    { "case_id": "...", "title": "Capital of France",
      "a": { "passed": true, "composite": 88 },
      "b": { "passed": true, "composite": 71 },
      "delta": { "composite": -17, "passed": 0, "latency": -0.4, "cost": -0.001 } }
  ]
}
```

`delta.passed` is `+1 = fixed`, `-1 = regressed`, `0 = same` — so a
single column tells you whether the new model/prompt fixed cases,
regressed them, or held steady.

---

## Studio Insights (model scorecards + the quality/cost frontier)

> Round‑7. The playground could *measure* everything — Arena latency & cost,
> judge composites, multi‑judge consensus, blind‑vote ELO — and *persist* it
> all. What it never did was step back and answer the question every LLM
> evaluation exists to answer: **which model gives me the best quality per
> dollar?** The new **Insights** mode does exactly that, and it invents no new
> data — it's the *same numbers* the rest of the app already produced, just
> aggregated, so it can never disagree with History, Judge, or Vote.

Hit **Insights** in the sidebar. Every Arena run on file is mined into:

- **The efficiency frontier** — a scatter of *quality (judge composite, 0‑100)
  vs cost ($/response, log scale)*. A model is **dominated** when another model
  is at least as good on quality **and** at least as cheap — you'd never
  rationally pick it. The non‑dominated set is the **frontier**: the only
  models worth choosing from. Frontier models are joined by a line and ringed;
  dominated ones fade. Bubble size = how many runs the model has been in,
  colour = provider. This is the chart you screenshot.
- **Model scorecards** — a sortable table: quality, cost/response,
  **quality‑per‑dollar** (with a comparison bar), latency, ELO + games, run
  count, and judge wins. Click any header to re‑sort (cost/latency sort
  cheapest/fastest‑first; everything else best‑first).
- **Headline KPIs** — total spend, **best value** (top quality‑per‑dollar on
  the frontier), top quality, cheapest, fastest, and a 7‑day spend trend
  (anchored on your latest run so it's deterministic).
- **Spend & quality over time** — daily spend bars with an avg‑top‑score line
  overlaid, so you can see cost creep against quality.
- **Spend by provider** — share‑of‑spend bars with mean quality per provider.
- **Copy brief** — a one‑click Markdown digest of the whole dashboard for a
  standup or a README.

### How the math works

```
avg_cost_m       = mean( cost_usd over every response from model m )
quality_m        = mean( judge composite over every judged response from m )   # 0–100
quality_per_$_m  = quality_m / avg_cost_m

m is on the frontier  ⇔  no other eligible model m' satisfies
                          quality_m' ≥ quality_m  AND  avg_cost_m' ≤ avg_cost_m
                          with at least one inequality strict
```

Only models with a judge composite **and** a positive cost are placed on the
frontier (those are the two axes); everything else is reported under
`unplaced` with a reason (`no_judge_score` / `no_cost`) so the UI can nudge you
to judge them. ELO is joined in from the blind‑vote replay so a model's
human‑preference rating sits right next to its quality and price.

### `GET /api/insights`

Optional `?min_appearances=N` drops models seen in fewer than N runs. Response
(truncated):

```json
{
  "success": true,
  "summary": {
    "total_spend": 0.182, "n_runs": 12, "n_judged_runs": 9, "n_models": 5,
    "spend_last_7d": 0.07, "spend_trend_pct": -18.4,
    "best_value":  { "key": "Google:gemini-flash", "quality_per_dollar": 71000.0, "avg_cost": 0.001 },
    "top_quality": { "key": "OpenAI:gpt-4o", "avg_composite": 89.0 },
    "cheapest":    { "key": "Google:gemini-flash", "avg_cost": 0.001 }
  },
  "scorecards": [{ "key": "Google:gemini-flash", "provider": "Google", "model": "gemini-flash",
                   "appearances": 4, "success_rate": 100.0, "avg_cost": 0.001,
                   "avg_composite": 71.0, "quality_per_dollar": 71000.0,
                   "efficiency_index": 100.0, "elo": 1503.1, "judge_wins": 1 }, ...],
  "frontier": { "points": [{ "key": "...", "quality": 89.0, "cost": 0.01,
                             "on_frontier": true, "dominated_by": [] }, ...],
                "frontier": ["Google:gemini-flash", "Anthropic:claude-haiku", "OpenAI:gpt-4o"],
                "n_eligible": 4, "n_on_frontier": 3, "unplaced": [] },
  "timeline":  [{ "day": 1700000000.0, "spend": 0.03, "runs": 1, "judged": 1, "avg_top_score": 90.0 }, ...],
  "providers": [{ "provider": "OpenAI", "spend": 0.14, "spend_share": 80.0, "avg_quality": 89.0 }, ...]
}
```

---

## 🏛️ Prompt Library (still here · Round 6)

> Round‑6. Every prompt engineer's daily question is "did my edit help?"
> The playground had every measurement (Arena, Judge, Vote, History) but
> no way to tie a *prompt revision* to the runs it produced. The new
> **Library** mode closes that loop.

Hit **Library** in the sidebar and you'll find a versioned prompt store.
Save the current Arena prompt as a new entry, iterate on the system prompt
or user template, and every saved revision lives on the version timeline
with its own per‑version run stats — `n_runs`, `avg_composite`,
`best_model`, and a 🏆 winner. **Click any two versions** and the diff
panel renders a unified diff (added lines green, removed red, hunk
headers) alongside a **score delta** computed from each version's judged
runs — so you can see whether tightening the system prompt actually moved
the needle.

The Library card surfaces:

- **Stats banner** — 4 gradient tiles (prompts · versions · linked runs ·
  avg composite across all judged) plus a "most iterated" pill row.
- **Score‑progression sparkline** per prompt row — judge_top_score per
  version v1 → vN as an SVG mini‑chart (gaps for un‑judged versions, no
  linear interpolation across them — a missing v3 doesn't lie about a
  trend).
- **Version timeline** — each version with score ring, run/cost/best‑model
  chips, change note, and Run / Diff buttons. HEAD is badged violet; the
  A/B diff endpoints get indigo/fuchsia rings.
- **Unified‑diff panel** — slate code surface with +/− line highlighting,
  per‑field deltas (system: +X/−Y, template: +X/−Y), overall similarity %,
  and a **Score Δ** chip computed from both versions' judged runs.
- **Arena integration** — when a version is loaded into Arena, the header
  shows a violet chip (`prompt · vN`) and any **Run Arena** auto‑attaches
  the resulting run to that version. A **Save as new version** button
  appears next to the chip, and a **Save to Library** button shows up for
  any *unlinked* Arena prompt.

### How the data loop works

```
1. Library → New prompt   → create_prompt() → v1 created
2. v1 → Run in Arena      → /compare { prompt_version_id: v1 } → run linked to v1
3. Run → Judge            → judge_top_score attaches → version_stats reflects it
4. Library → New version  → add_version() → v2 created (idempotent if identical)
5. v2 → Run in Arena      → run linked to v2 → judge → score
6. Library → click v1+v2  → /prompts/diff → unified diff + score_delta = score(v2) − score(v1)
```

If `score_delta > 0`, your edit helped. If it's *very* negative, you
regressed — the diff hunks tell you exactly which lines did it.

### Schema (shares ``history.db``)

```
prompts          (id, name, created_at, updated_at, current_version_id,
                  starred, tag, note)
prompt_versions  (id, prompt_id, version_num, system_prompt, user_template,
                  created_at, parent_version_id, note)
runs.prompt_version_id   -- new nullable FK, added via idempotent ALTER on boot
```

`add_version()` is **idempotent on identical content** — clicking "Save
new version" twice with no edit between doesn't create a sibling row.
`delete_prompt()` cascades versions but **preserves runs** (their
`prompt_version_id` becomes a dangling pointer — deliberate, so the audit
trail of "which prompt produced this answer" survives prompt cleanup).

### `POST /api/prompts/diff`

```json
{ "a": "<version_id_a>", "b": "<version_id_b>" }
```

Response (truncated):

```json
{
  "success": true,
  "diff": {
    "a": { "version_num": 1, "system_prompt": "...", "user_template": "...", "stats": { "n_runs": 1, "avg_composite": 50.0, "best_model": "OpenAI:gpt-4o" } },
    "b": { "version_num": 2, "system_prompt": "...", "user_template": "...", "stats": { "n_runs": 1, "avg_composite": 90.0, "best_model": "Anthropic:claude-3-5-sonnet-latest" } },
    "hunks": [{ "header": "@@ -3,5 +3,6 @@", "lines": [{ "type": "ctx", "text": "..." }, { "type": "add", "text": "Keep to 1 line." }] }],
    "stats": { "system":   { "added": 1, "removed": 1, "similarity": 0.66 },
               "template": { "added": 1, "removed": 0, "similarity": 0.85 },
               "overall":  { "added": 2, "removed": 1, "similarity": 0.71 } },
    "score_delta": 40.0
  }
}
```

---

## 🏛️ Multi‑Judge Consensus (still here · Round 5)

> Round‑5. A single judge is biased — self‑preference, format prejudice,
> "longer must be better." A panel isn't. Now you can run up to **6 judges**
> on the same Arena run, in parallel, and see where they agree and where
> they don't.

Open the rubric editor and you'll see a new **Judge panel** — the primary
judge picker is row #1, and a `+ Add judge to panel` button adds rows up to
#6. When the roster has ≥ 2 judges, the **Judge responses** button morphs
into **Run consensus · K judges** (fuchsia gradient instead of amber) and
fans the same judge prompt out to every judge in parallel — wall time is
the slowest judge, not the sum.

The consensus card surfaces:

- **Confidence-bar leaderboard** — per candidate: panel mean composite,
  std‑dev, full min–max range overlay, and a `votes/n_judges` chip showing
  how many judges put it at #1. Sorted by mean (ties broken by winner-votes).
- **Per‑criterion Fleiss' kappa** — categorical inter‑rater agreement on
  each 1–5 rubric criterion, with κ ≥ 0.61 painted green (substantial),
  0.21–0.61 amber (moderate / fair), < 0.21 rose (slight / disagreement).
  Hover for the Landis‑Koch label.
- **Per‑judge top pick** — each judge's #1 next to the panel‑mean #1 with a
  ✓ agrees / ✗ dissents chip per judge.
- **Most-contested** highlight — the candidate with the highest composite
  std-dev gets called out: judges spread X–Y (±σ from mean μ).
- **Failed judges** surface inline (missing key, upstream error) — the
  panel runs with whoever responded.
- Per Arena card, the score ring shows `panel μ` instead of `score`, with
  `±std`, the min-max range, and the `winner_votes/n` chip in a row below.

### How the math works

```
composite_i,j = Σ_c ((s_i,j,c − 1) / 4) · w_c   × 100      # per judge i, candidate j
mean_j        = (1/K) · Σ_i composite_i,j                  # panel mean
σ_j           = sample std dev across K judges
winner_votes_j = | { i : argmax_j composite_i,j } |        # # of judges who picked j
```

For Fleiss' κ on criterion c, judges' 1–5 scores are categorical:

```
P_e = Σ_k p_k²              (chance agreement from category marginals)
P̄   = (1/N) · Σ_j P_j        (mean per-item agreement)
κ_c = (P̄ − P_e) / (1 − P_e)  ∈ [−1, 1]
```

`κ = 1` is perfect agreement; `0` is chance; negative is systematic
disagreement (judges who pick *different* categories item-to-item). Overall
κ is the mean of per-criterion κs.

The full consensus block is persisted onto the Arena run under
`payload.consensus`; a back‑compat `payload.judge` is also written from the
panel means so the History tab keeps rendering the run with no special
casing.

### `POST /api/judge/consensus`

```json
{
  "prompt":        "...",
  "system_prompt": "...",
  "candidates":    [{"provider":"OpenAI","model":"gpt-4o","response":"...","status":"success"}, ...],
  "judges":        [{"provider":"Anthropic","model":"claude-3-5-sonnet-latest"},
                    {"provider":"OpenAI",   "model":"gpt-4o"},
                    {"provider":"Google",   "model":"gemini-1.5-pro"}],
  "rubric":        [{"name":"Correctness","description":"...","weight":0.35}, ...],
  "run_id":        "<existing arena run id>"
}
```

Response (truncated):

```json
{
  "success":   true,
  "rubric":    [...],
  "consensus": [{ "candidate": 0, "provider": "...", "model": "...",
                  "composite_mean": 82.5, "composite_std": 4.2,
                  "composite_min": 78, "composite_max": 87,
                  "per_criterion": {"Correctness": {"mean": 4.66, "std": 0.47, "votes":[5,5,4]}, ...},
                  "winner_votes": 2, "n_judges": 3,
                  "rationales": [{"judge":"...","text":"..."}, ...] }, ...],
  "leaderboard": [...],
  "winner": 0,
  "agreement": {
    "per_criterion": {"Correctness": {"fleiss_kappa": 0.42}, ...},
    "overall": {"fleiss_kappa": 0.37, "mean_composite_std": 4.2, "panel_winner": 0, "n_judges": 3},
    "per_judge": [{"provider":"...","model":"...","their_top":0,"agrees_with_panel":true}, ...]
  },
  "judges": [...],
  "judges_failed": [],
  "panel_meta": {"n_judges": 3, "n_failed": 0, "max_latency": 4.1,
                 "total_cost_usd": 0.018, "total_input_tokens": 3200, "total_output_tokens": 950}
}
```

---

---

## 🏛️ Personal Chatbot Arena (still here · Round 4)

> Round‑4. Your own LMSYS‑style arena, fed by your own runs.

A new **Vote** mode samples pairs from your run history with provider/model
labels hidden, you pick a winner (A · B · Tie · Both bad), and an
**ELO replay** keeps a live leaderboard. Cast a few votes and you'll see:

- A 🥇/🥈/🥉 leaderboard with rating, games, W/L/T, win-rate, and the last
  8 results as a colour-coded form strip.
- A **head-to-head matrix** (top 8 models, hue-graded win rate per cell).
- A **judge ↔ human agreement** card — for every decisive vote on a judged
  run, did your pick match the LLM judge's #1? Per-model agreement %
  included.
- A **recent votes feed** with one-click undo (the leaderboard is replayed
  every call, so undo is exact).
- Keyboard shortcuts: **`1`** A wins · **`2`** B wins · **`=`** Tie ·
  **`0`** Both bad · **`N`** next pair.

### How the math works

```
expected_a = 1 / (1 + 10^((rating_b - rating_a) / 400))
rating_a' = rating_a + K · (score_a - expected_a)
```

* `K = 24` (FIDE-blitz default · env-tunable via `LLM_ELO_K`).
* `prior = 1500` (env-tunable via `LLM_ELO_PRIOR`).
* **Tie** → score 0.5 / 0.5.
* **Both bad** → no rating change (no signal in either direction).
* The leaderboard **replays the entire vote log** on every call — so deleting
  a misclick rewinds it cleanly, and changing K reshapes the ranking
  without losing data.

### Pair sampling

`GET /api/arena/pair` walks the most recent runs (newest first), enumerates
every cross-pair within each, and biases towards **under-played** match-ups
so a power-user voter doesn't get the same pair twice in a row. The
provider/model identities never reach the client until the vote is cast —
the response surfaces them under `_truth` which the panel keeps in
component state.

### History → Vote deeplink

Every History row with ≥ 2 successful candidates now shows a **Vote**
button. Clicking it pins the Vote panel to that specific run, samples a
pair *from inside it*, and cycles to a fresh pair from the same run on
"Next" — making it easy to triple-vote a single arena run when you want
high-confidence ELO movement.

---

## 🏛️ Run History (still here · Round 3)

> Every Arena run is persisted. Filter, star, tag, re‑run, and **diff**
> any two runs side‑by‑side.

After Arena, after Judge, the run lands in **History**: prompt, system prompt,
every candidate's response with metrics, the arena winners, and — if you
clicked Judge — the rubric, verdicts, leaderboard and judge metadata.
Filter by free-text search, provider chips, judged-only, starred-only.
Hold ⌘/Ctrl + click a second row to pin it as a diff partner.

A single SQLite table `runs` (`database/history.db`, gitignored) where the
heavyweight payload lives in a JSON `payload` column and **everything we
filter, sort, or aggregate on** is mirrored as an indexed scalar column.
The Vote module's `votes` table piggy-backs on the same DB file so a single
backup captures everything.

---

## 🏛️ LLM‑as‑Judge auto‑eval (still here · Round 2)

> One prompt → N answers → an LLM judge scores them all.

Hit **Judge responses** after a run and another model scores every candidate
against a 5‑criterion rubric (Correctness · Completeness · Clarity ·
Conciseness · Format) on a 1‑5 scale. Per‑criterion bars, a 0‑100 weighted
composite, a one‑sentence rationale, a leaderboard, and a 🏅 *judge pick*
badge. Editable rubric, paranoid JSON extraction, judge cost & latency
tracked, results auto-persisted into history.

> Composite formula: `Σᵢ ((scoreᵢ − 1) / 4) · weightᵢ` × 100, where weights
> are renormalised to sum to 1 before scoring.

## ⚔️ Arena mode (still here · Round 1)

- **Parallel fan‑out** to OpenAI, Anthropic, Google (up to 6 candidates).
- **Per‑card metrics**: latency · total tokens · estimated **$ cost**.
- **Surface‑metric badges**: 🏆 fastest · 💰 cheapest · 📝 most verbose.
- **Headline tiles**: models tested, successes, wall‑clock runtime, total spend.
- **One‑click copy** per response.
- Shared system prompt + parameters across every candidate.

`/api/compare` runs each provider in a `ThreadPoolExecutor` and catches
per‑candidate errors so a missing API key never kills the siblings.

---

## 🚀 Everything else

- **Universal mode** — classic chat against a single provider/model with
  conversation editing, message toggling, duplicate, reorder, "run from
  here" branching, system prompt dialog, reasoning‑effort presets for
  o‑series / opus models, drag‑and‑drop JSON import.
- **August mode** — forward payloads to a custom `August` service
  (`pkey` / `pvariables`).
- **API key manager** — masked key status per provider, in‑app save
  writing to the backend `.env`.
- **Full debug panel** — provider, model, input/output/total tokens,
  latency, request id, status, timestamp, cost.
- **Cost estimate on every single‑chat call** (not just Arena).

## 🖼️ Screenshots

![UI Screenshot](Playground_img.png)

## ⚙️ Setup

```bash
# 1. Clone and enter
git clone https://github.com/Aryanharitsa/Projects.git
cd Projects/LLM_Playground

# 2. Backend
cd llm_playground_backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# create a .env with the keys you have (any subset works):
#   OPENAI_API_KEY=...
#   ANTHROPIC_API_KEY=...
#   GEMINI_API_KEY=...
#   AUGUST_API_BASE_URL=...    # optional
#   AUGUST_API_KEY=...         # optional
#   LLM_ELO_K=24               # optional (default)
#   LLM_ELO_PRIOR=1500         # optional (default)
python src/main.py              # serves on :5050

# 3. Frontend (in a second terminal)
cd ../llm_playground_frontend
pnpm install                    # or npm install --legacy-peer-deps
pnpm dev                        # Vite on :5173
```

Open `http://localhost:5173`, pick **Arena**, fan out a prompt, then flip
to **Vote** and start judging blind. **History** persists everything.

## 🗺 API surface

| Method | Path                       | Purpose                                                |
|--------|----------------------------|--------------------------------------------------------|
| GET    | `/api/health`              | liveness probe                                         |
| GET    | `/api/providers`           | provider → availability + known models                 |
| GET    | `/api/models/:provider`    | model list (dynamic when provider supports listing)    |
| GET    | `/api/parameters/:prov`    | supported params + `supports_json_mode` / `…reasoning…` |
| GET    | `/api/pricing`             | per‑model input/output $/1M token table                |
| GET    | `/api/rubric`              | default judge rubric (criteria + weights)              |
| POST   | `/api/chat`                | single‑provider chat (returns `cost_usd` in debug)     |
| POST   | `/api/compare`             | **Arena** — parallel fan‑out, winners, total cost      |
| POST   | `/api/judge`               | **LLM‑as‑judge** — score Arena responses with rubric   |
| POST   | `/api/judge/consensus`     | **Panel judge** — K judges in parallel + κ agreement   |
| GET    | `/api/history`             | paginated, filterable list of runs                     |
| GET    | `/api/history/:run_id`     | full payload for one run (responses + judge)           |
| POST   | `/api/history/:run_id/meta`| set `tag` / `note` / `starred` on a run                |
| DELETE | `/api/history/:run_id`     | delete a run                                           |
| GET    | `/api/history/stats`       | aggregate metrics + top judge winners                  |
| POST   | `/api/history/diff`        | side‑by‑side diff of two runs                          |
| GET    | `/api/arena/pair`          | **blind A/B pair** sampled from history                |
| POST   | `/api/arena/vote`          | record a vote — returns the updated leaderboard         |
| DELETE | `/api/arena/vote/:id`      | undo a vote (rewinds the ELO replay)                   |
| GET    | `/api/arena/leaderboard`   | ELO leaderboard (k / prior / since / min_games params) |
| GET    | `/api/arena/matrix`        | head‑to‑head wins matrix for top‑N                     |
| GET    | `/api/arena/agreement`     | judge ↔ human agreement % + per‑model breakdown        |
| GET    | `/api/arena/recent`        | recent votes feed                                      |
| GET    | `/api/arena/stats`         | top‑of‑page voting stats                               |
| GET    | `/api/prompts`             | **Library** — list versioned prompts + roll‑up stats   |
| POST   | `/api/prompts`             | create a new prompt (auto‑creates v1)                  |
| GET    | `/api/prompts/:id`         | full prompt with every version + per‑version stats     |
| DELETE | `/api/prompts/:id`         | delete prompt + version chain (runs are preserved)     |
| POST   | `/api/prompts/:id/meta`    | rename / star / tag / note                             |
| POST   | `/api/prompts/:id/versions`| append a new version (idempotent on identical content) |
| GET    | `/api/prompts/:id/versions/:vid/runs` | runs linked to a specific version          |
| POST   | `/api/prompts/diff`        | **unified diff** of two versions + score Δ            |
| GET    | `/api/prompts/stats`       | library‑level dashboard banner stats                   |
| GET    | `/api/insights`            | **Insights** — scorecards + efficiency frontier + spend |
| POST   | `/api/export`              | canonicalise a chat session as JSON                    |
| GET    | `/api/key-status`          | masked key presence per provider                       |
| POST   | `/api/save-keys`           | persist keys to `.env`                                 |

### `/api/arena/pair` query params

| Name        | Type   | Notes                                                       |
|-------------|--------|-------------------------------------------------------------|
| `run_id`    | string | sample within a specific run (deeplink from History)        |
| `exclude_a` | string | model key already shown as A (de-dup refresh)               |
| `exclude_b` | string | model key already shown as B                                |

### `/api/arena/leaderboard` query params

| Name        | Type   | Notes                                                       |
|-------------|--------|-------------------------------------------------------------|
| `k`         | float  | K-factor override (default 24, env `LLM_ELO_K`)             |
| `prior`     | float  | initial rating (default 1500, env `LLM_ELO_PRIOR`)          |
| `since`     | float  | unix epoch lower bound on votes                             |
| `min_games` | int    | drop models with fewer than this many votes                 |

## 📂 Project structure

```
LLM_Playground/
├── llm_playground_backend/
│   └── src/
│       ├── main.py                  # Flask app + CORS + static host
│       ├── pricing.py               # per-model $/1M token table
│       ├── judge.py                 # rubric + single + consensus judge engine + Fleiss' κ
│       ├── history.py               # SQLite-backed run store + diff/stats + consensus persistence
│       ├── vote_arena.py            # ELO replay + pair sampler + agreement
│       ├── prompts.py               # versioned prompt library + unified diff + run links
│       ├── insights.py              # ⬅ NEW · scorecards + Pareto efficiency frontier + spend roll-up
│       ├── routes/
│       │   ├── llm.py               # /chat, /compare, /judge[/consensus], /history/*, /arena/*, /prompts/*, /insights, …
│       │   ├── keys.py              # /key-status, /save-keys
│       │   └── user.py
│       ├── providers/               # OpenAI / Anthropic / Gemini / August
│       └── models/
└── llm_playground_frontend/
    ├── src/
    │   ├── App.jsx                  # Universal + August + Arena + History + Vote + Library + Insights modes
    │   ├── services/api.js          # typed client (incl. arena* + prompt*)
    │   └── components/
    │       ├── HistoryPanel.jsx     # filters · run list · detail · compare-two-runs
    │       ├── VotePanel.jsx        # blind compare + leaderboard + matrix + agreement
    │       ├── PromptLibrary.jsx    # versioned prompts · timeline · unified diff · score Δ
    │       ├── InsightsPanel.jsx    # ⬅ NEW · efficiency frontier · scorecards · spend timeline
    │       └── ui/                  # shadcn primitives
    └── vite.config.js
```

## 🛤 Roadmap

- Response streaming (SSE) with live tokens/sec per card
- ~~Blind A/B voting → ELO leaderboard across saved runs~~ ✅ shipped
- ~~Prompt library with diff'd versions~~ ✅ shipped
- ~~Auto‑eval rubrics (LLM‑as‑judge) with exportable scoring sheets~~ ✅ shipped
- ~~Persisted judged runs as a queryable history~~ ✅ shipped
- ~~Multi‑judge consensus (run K judges, average scores, surface disagreement)~~ ✅ shipped
- ~~Cost/quality efficiency frontier across all evaluated models~~ ✅ shipped
- Saved comparisons → permalinks
- Vote-driven prompt regeneration ("which prompts move ELO most?")

## 👨‍💻 Author

Built with ❤️ by Aryan D Haritsa · Student @ PES University · AI &
Full‑stack enthusiast.
