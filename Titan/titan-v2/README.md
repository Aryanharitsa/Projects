# TITAN v2

**Trusted Identity & Transaction Authentication Network.**
Document-grade KYC + on-chain attestation + a deterministic, explainable AML
risk engine **with built-in sanctions screening**, a real **case management
workflow**, a **network-intelligence layer** that catches money-laundering
patterns single-account scoring misses, a **case-detail network panel** that
collapses both into one analyst surface, **and** — as of day-30 — an
**auto-classified laundering typology** on every alert. The pipeline now
names the playbook (`SMURF`, `LAYER`, `TBML`, `MULE`, `SANCEV`, `INTEG`),
quantifies how well the evidence fits, and pre-writes the SAR §3
narrative — turning a wall of factor bars into "this looks like
smurfing — here's the 86% confidence, here's the contributing evidence,
here's the freeze-and-investigate paragraph".

> **Day-85 — Horizon · regulatory-change impact simulator.**
> Every prior TITAN surface answers "given today's rules, what is this
> case?". Horizon answers the question every MLRO loses sleep over the
> night before a policy revision ships: *"Which of the six-hundred cases
> in the queue would flip band? Which cleared cases would re-fire? Which
> analyst decisions become inconsistent with the new rules? Which
> detectors do the damage — and which do nothing?"*. New
> `apps/ai-aml/horizon.py` (~1,100 LOC, pure stdlib, **zero new deps**)
> is a fully-deterministic replay engine: `simulate(proposal, cases) →
> HorizonReport`. The proposal bundles every knob an approver actually
> touches — per-detector weight overrides, forced-disable list, sanctions
> similarity gate, new SDN entries (fuzzy-matched against every subject
> and counterparty captured on the frozen snapshot), FATF jurisdiction
> uplift / relief, alert-fire threshold, band cutoffs. The engine
> recovers each detector's underlying **intensity** from the snapshot
> (`points / weight`), re-projects it under the new weight, folds in the
> proposal-sourced signals (new SDN hits floor the sanctions_hit intensity
> at 0.75, uplift geos add `JURISDICTION_UPLIFT` per matching edge, band
> cutoffs apply after score recomputation), then rolls the four axes into
> a first-match-wins **verdict ladder** — `material_flip` (alert-fire
> boolean flipped, or band moved ≥ 2 steps), `band_shift` (one-step move
> within alert bands), `touched` (score-only movement above the touch
> epsilon), `stable` (else). Six curated **presets** ship in the box —
> `OFAC uplift`, `Structuring hardening`, `FATF grey-list refresh`,
> `Noise reduction`, `New SDN additions`, `Band recalibration` — every
> one a real MLRO scenario. The aggregate exposes the six numbers a
> change-management review actually asks for: total cases replayed,
> per-verdict counts, alert-flip waterfall (`cleared→alert`,
> `alert→cleared`, `still_alert`, `still_cleared`), the full **band
> transition matrix** (4×4 counts), a **detector contribution ranking**
> (sum of |Δpoints| across the backlog), and a `suggested_action`
> verdict — `defer / pilot / roll_out / investigate` — that rolls
> everything up to one recommendation.
>
> **Surface** — new `/horizon` route between AML Console and KYC.
> Action-tinted hero (verdict tint on the whole banner), four stat
> tiles (cases replayed, cleared→alert, alert→cleared, material flips)
> and a signed "suggested action" pill. Horizontal **preset picker**
> with six chips, each a real regulatory scenario. **Proposal chip
> row** — one chip per material config edit (weight delta vs baseline,
> disabled detectors, sanctions gate change, new SDN count, uplift /
> relief countries, band cutoffs), so the change is legible without
> reading JSON. **Backlog waterfall** — hand-rolled stacked bar showing
> the four alert-flip shares. **4×4 band-transition matrix** with
> destination-band-tinted cells, off-diagonal cells count as flips.
> **Detector contribution bars** sorted by |Δ|. **Interactive weight
> editor** — nine sliders (0..MAX_WEIGHT) plus on/off toggles let the
> approver layer edits on top of the preset; a Re-simulate button hits
> the live `/aml/horizon/simulate` endpoint against the fixture case
> set, so the whole page reflows in one round-trip. **Case impact
> table** (filterable by verdict) → **per-case drill-down** with a
> hand-rolled score arc (old-score dashed ring, new-score coloured
> ring at inner radius, delta stamped in the middle), per-detector Δ
> rows with the engine's own reason strings, fired-vs-dropped sanctions
> block (proposal-sourced hits get a rose "new SDN" badge). Rules
> footer exposes the engine version, verdict ladder chips, default
> tunables, and a one-click **markdown impact-memo download** — the
> paste-into-a-change-management-ticket document, deterministic
> byte-for-byte. Engine: `titan-horizon/1.0.0`. AML: `titan-aml/1.16.0`.

> **Day-80 — Nexus · beneficial ownership discovery + sanctions/PEP reach.**
> Every prior TITAN surface reasons about a *transaction* or an *alert*.
> Nexus reasons about the *legal structure* — who really owns and controls
> this legal entity once you unwind the holding companies, the nominee
> directors, and the offshore chain. It answers four regulator questions
> in one deterministic pass: **FinCEN CTA** (who is the ≥25% beneficial
> owner?), **OFAC 50% Rule** (does aggregate sanctioned control block the
> target, whether or not it appears on the SDN list?), **FATF Rec. 24**
> (how layered is the corporate structure?), and **EU 6AMLD** (do nominee
> or trustee edges obscure the UBO?). New `apps/ai-aml/nexus.py`
> (~1,000 LOC, pure stdlib, **zero new deps**) models the ownership
> graph, walks every simple path from any root to any target, and sums
> the products of edge percentages — the standard beneficial-ownership
> arithmetic every regulator expects. Cycles are legal in reality
> (mutual-holding companies) so the engine tolerates them, tags them,
> and treats a repeated node in a walk as a zero-weight extension.
>
> **UBO ladder** — `beneficial_owner` (aggregate ≥ 25%), `screening_
> required` (10–24%), `corporate_owner` (control chain still passes
> through a company — traverse upstream), `de_minimis` (below the
> screening floor). A **substantial-control** edge (edge type `control`)
> always upgrades to `beneficial_owner` regardless of percentage — a
> senior officer with 2% shares is still a UBO under the CTA. Only
> natural persons qualify; corporate controllers get labelled and the
> traversal continues.
>
> **Sanctions reach** — for every sanctioned root `S` and every target
> `T`, `eff(S, T) ≥ 0.50` → `BLOCKED_REACH` (target inherits SDN status
> per the OFAC 50% rule); `≥ 0.25` → `REPORTABLE_REACH`; anything else
> → `EXPOSED_LINK`. Aggregation across multiple blocked persons follows
> the OFAC "aggregate across all blocked persons" rule so two sanctioned
> individuals holding 30% and 25% jointly block a target even though
> neither alone would. **PEP reach** uses the same arithmetic with
> softer 25%/10% thresholds and flips the risk grade instead of blocking.
>
> **Opacity score** — a composite [0, 100] per target computed from
> seven components (chain depth, shell-node share, offshore share,
> nominee/trustee share, controller dispersal, cycle penalty,
> thin-capital share) with weights that sum to 1.0. Verdict ladder
> collapses everything into five explicit rungs — `blocked_by_
> sanctions`, `sanctions_exposed`, `pep_edd_required`, `opaque_
> structure`, `transparent_structure` — each tied to a hard threshold
> so an examiner can trace every conclusion back to a constant in
> `get_rules()`.
>
> **Surface** — new `/nexus` route between Triage and Drift.
> Verdict-tone-tinted hero + 148-px opacity conic ring + entity chips
> (kind / jurisdiction / risk / shell indicators); a 7-tile portfolio
> strip (entities · edges · offshore nodes · shell-flagged · sanctioned
> hits · PEP hits · avg opacity) plus a verdict-distribution ribbon;
> a searchable verdict-tinted **target picker** across the seven
> bundled topologies; a hand-rolled **radial ownership-chain SVG**
> — target anchored at bottom-centre, controllers spread across the
> top, path stroke width scaled to weight, sanctioned paths glow rose
> and PEP paths glow amber, every intermediate holding node
> in-lined on its chain, per-path weight labels at midpoint; a
> **controllers panel** with per-controller aggregate bars marked at
> the 25% CTA threshold and UBO-class badges; a two-part **sanctions
> + PEP nexus panel** with tri-band aggregate meters and per-hit
> reach-code rows; a **7-bar opacity breakdown** with raw values,
> weights, and contribution; a **top-10 ownership paths table** with
> the exact percentage sequence for each chain; a **downstream reach
> viz** — pick any sanctioned or PEP controller and see every
> downstream target arranged on concentric depth rings, node radius
> scaled to aggregate reach, coloured by OFAC band; and a verdict-
> ladder footer with the FinCEN/OFAC/PEP thresholds and the corpus
> hash for reproducibility. A one-click **memo export** (`export.md`)
> composes a paste-into-case-note document with the UBO table,
> sanctions/PEP nexus, top ownership paths, opacity components, and
> any cycles detected. Deterministic — same `(entities, edges)` →
> identical bytes, identical path IDs, identical opacity score.
> Engine: `titan-nexus/1.0.0`. AML: `titan-aml/1.15.0`.

> **Day-75 — Triage · cleared-case suppression + FP mining.**
> Every prior TITAN surface *judges* one alert — how severe, what
> typology, what network, what precedent. Real AML operations run at
> a 90-95% false-positive rate, so the *opposite* question is where
> the analyst hours actually go: *"is this alert noise? which of
> today's queue looks like a signature we've routinely cleared
> before?"*. New `apps/ai-aml/triage.py` (~900 LOC, pure stdlib,
> **zero new deps**) mines the case store's `cleared` vs `sar_filed`
> disposition history and answers that question deterministically.
> Every candidate alert gets a **signature** — the top-K (default 4)
> firing factor names — from which the engine builds every
> singleton + unordered pair combo (a 4-factor signature → 4
> singletons + 6 pairs = 10 combos). For each combo *c* it tallies
> `n_seen`, `n_cleared`, `n_sar` across the closed corpus, computes
> a Beta-Bernoulli clearance posterior with Laplace α = 0.5
> (`p_clear(c) = (n_cleared + α) / (n_seen + 2α)`), and takes the
> `log₂` lift over the portfolio prior. Combos aggregate through an
> evidence-weighted mean into a bounded score `S = tanh(Σ w(c)·lift(c)
> / |combos_scored|)`; `suppression = (S+1)/2 ∈ [0,1]`.
>
> Six explicit **verdict rungs** — `suppress_high_confidence`,
> `suppress_review_lightly`, `no_prior_signal`, `elevate_review`,
> `escalate_critical`, `insufficient_history` — each tied to a
> hard-coded S threshold and a support gate, so every decision is
> regulator-auditable back to the exact case IDs it cites. A
> **sanctions veto** caps `S` from *above* at −0.2 whenever
> `sanctions_hit` is in the signature: a sanctions-touching alert
> can never suppress, but escalation propagates through unchanged.
> Combos with fewer than `MIN_SUPPORT_ANY = 3` precedents are
> excluded from the aggregate; combos below `MIN_SUPPORT_STRONG = 5`
> weight linearly so under-supported evidence never dominates.
>
> **Surface** — new `/triage` route between Precedent and Drift:
> verdict-tone-tinted hero banner + a 132-px suppression conic ring
> + query-signature chips (sanctions_hit gets a rose ⛔ marker); a
> 4-tile aggregate strip (closed corpus / portfolio prior / aggregate
> S / suppression %); a searchable priority-tinted candidate picker
> with a *sanctions-touching only* filter; a per-case **scored-combo
> table** with symmetric log₂-lift bars (rose→amber→teal, centred on
> zero), a cleared-vs-SAR count chip, and a support pill; a **9×9
> factor-pair suppression matrix** shaded by lift with per-cell
> clearance-rate labels + hover-detail row; two **evidence panels**
> — up to 3 cleared precedents + up to 3 SAR precedents that share
> ≥ 2 signature factors, each with disposition/band/typology chips
> and a shared-factor chip row; two portfolio leaderboards (top
> noise combos + top signal combos) below the matrix; and a verdict-
> ladder footer where the current verdict lights up with a matching
> glow. A one-click seed of a **12-family FP-rich supplementary
> corpus** (`round_amount-alone`, `fan_in-alone`, `round_amount+fan_in`,
> `velocity+high_risk_geo` on the noise side; `structuring+sanctions`,
> `round_trip+high_risk_geo`, `structuring+velocity`, `adverse_media+sanctions`
> on the signal side; plus two mixed-signal MULE-flavoured combos)
> takes the miner from cold-start to a demo-ready ~76-case terminal
> corpus in one POST. Deterministic — same case store snapshot →
> identical bytes returned, identical case IDs cited, identical
> matrix. Engine: `titan-triage/1.0.0`.

> **Day-70 — Precedent · the case-similarity + disposition prior.**
> Every prior TITAN surface *judges* one case in isolation — `risk`
> fires rules, `typology` names the playbook, `network` finds cross-
> account links, `lineage` follows value through time, `pulse` compares
> this week to last, `profile`/`peer`/`drift` compose the customer view.
> None of them answer the analyst's *very first* question when a new
> case lands on their queue: *"have we seen a case like this before,
> and how did it end?"*. New `apps/ai-aml/precedent.py` (~800 LOC, pure
> stdlib, **zero new deps**) is that answer. Given an open case it
> extracts a **19-dim block-partitioned feature vector** — 9-dim
> normalized detector firing intensities, 6-dim primary-typology one-hot
> weighted by confidence, 2-dim log10 inbound/outbound totals, 2-dim
> band ordinal + sanctions gate — and runs a **block-weighted cosine
> kNN** over the entire case store (block weights: `factor 0.55 ·
> typology 0.20 · posture 0.15 · amount 0.10`). Every match ships a
> **similarity-driver breakdown** (which axes contributed) and a
> **top-6 delta view** (which axes distinguish it from the query).
> Terminal precedents feed a **Bayesian disposition prior** with
> Laplace smoothing (α = 0.5 per class) — a lone precedent doesn't
> collapse the posterior to 100% — plus a **median time-to-resolution**
> from the same set. The engine emits one of five explicit
> recommendation verdicts — `file_sar_probable`, `expedite_clearance`,
> `weigh_evidence`, `novel_investigate`, `insufficient_precedent` —
> tied to named precedent IDs, so every recommendation is regulator-
> auditable. **Surface** — new `/precedent` route between Lineage and
> Drift: verdict-accent-tinted hero banner + query summary + 4 aggregate
> tiles (precedent count / posterior P(SAR) / median TTR / considered
> corpus), a searchable candidate picker, a Bayesian posterior bar with
> 50/50 base-rate reference, k precedent cards each with a conic
> similarity ring + disposition/band/typology chips + top-factor
> summary + block-attribution bars + delta chips, paste-able "precedent
> memo" markdown export, and a one-click seed of the bundled 30-case
> six-family demo portfolio (`SMURF-heavy · LAYER-cycle · MULE-
> passthrough · TBML-cross-border · SANCEV-watchlist · Baseline-quiet`)
> chosen so retrieval exercises every rung of the recommendation
> ladder. Deterministic — same case store + same query case → identical
> ranking, identical posterior, identical recommendation. Engine:
> `titan-precedent/0.1.0`.

> **Day-65 — Lineage · the temporal fund-flow tracer.** Every prior
> TITAN surface answers a *structural* or *aggregate* question — `risk`
> scores one batch, `network` shows who an account is *connected to*,
> `typology` names the playbook, `profile` composites the customer's
> risk *today*, `pulse` shows what *changed* across the book. None of
> them answer the question a real investigator opens with the moment a
> SAR draft lands on their desk: *"where did this money come from,
> where did it go, and how much of it can I actually trace from origin
> to destination?"*. New `apps/ai-aml/lineage.py` (~900 LOC, pure
> stdlib, **zero new ML deps**) is a single deterministic function
> `compute_lineage(transactions, seed, direction, max_depth,
> window_days) → LineageReport`. It walks the transaction graph
> outwards from the seed (`forward` = downstream, `backward` =
> upstream, `both` = the union), bounded by depth and time window;
> runs a **FIFO lot tracer** over every account (the same convention
> every forensic accountant uses for commingled funds — when a lot
> leaves, it consumes the oldest inflow first, splitting the upstream
> attribution proportionally onto the outflow); and emits a per-account
> `provenance` map showing what fraction of *current* balance is
> attributable to each upstream source.
>
> Six **flow-shape detectors** then run over the built DAG — patterns
> single-account scoring *can't* see because they only exist *across*
> the trail: `smurf_chain` (≥5 sub-threshold senders → funnel → ₹1L+
> wire out), `round_trip` (≥20% of seed outflow returns via ≥2 hops),
> `pass_through` (high fan-in + fan-out + ≤12% retention = mule),
> `integration` (round-amount transfer into clean-asset venue —
> real-estate, jewellery, auto), `velocity_ramp` (mean hop interval
> shrinks across the trail — rush-to-layer signal), `geo_hopping` (≥3
> distinct jurisdictions touched). Each match emits a 0..1 confidence,
> ranked evidence chips, contributing-node ids, and a recommended
> action.
>
> | Code | Pattern | Severity floor |
> |---|---|---|
> | `smurf_chain`   | Many sub-threshold senders → funnel → wire out | high |
> | `round_trip`    | Layering loop — funds return to seed | critical |
> | `pass_through`  | Mule — fan-in + fan-out, retention ≤12% | medium |
> | `integration`   | Round-amount transfer into a clean-asset venue | medium |
> | `velocity_ramp` | Hop interval shrinks across the trail (rush-to-layer) | medium |
> | `geo_hopping`   | ≥3 distinct jurisdictions touched | high |
>
> **Trail score** composes five normalised factors —
> `0.40·depth + 0.25·amount + 0.15·pattern + 0.10·geo + 0.10·suspicious_node` —
> with each sub-score, weight, and contribution echoed back so an
> auditor can see *why* it scored what it did. A first-match-wins
> mood ladder (`calm < watch < active < critical`) writes the
> headline and advisory line. The **plan-of-action** is the action
> layer: prioritised checklist that *names the TITAN tab each step
> lives in* — freeze in **Cases**, re-anchor in **Profile**, confirm
> structure in **Network** — so the analyst can click straight from
> the trail into the next surface.
>
> Five new endpoints in the AML service: `GET /aml/lineage/rules`
> (every threshold + score weight, auditor-facing), `GET
> /aml/lineage/seeds` (curated picker for the bundled sample),
> `GET /aml/lineage/sample` (28-tx three-arm laundering demo —
> placement → layering → integration plus a partial round-trip and a
> velocity ramp, lights up at least four of the six detectors), `POST
> /aml/lineage/trace` (full trace with caller-supplied transactions),
> `GET /aml/lineage/export.md` (paste-able SAR §3 exhibit, ~2.5 KB).
> Mirrored through the gateway in `apps/api/main.py` so the frontend
> has one origin. AML service version bumped `1.11.0 → 1.12.0`.
>
> **Surface** — new `/lineage` route between **Network** and **Drift**
> in the nav. Hero panel with a mood-tinted breathing conic ring,
> headline, seed picker, direction + depth + window controls, markdown
> exhibit download. 6-tile vital-signs strip (nodes · edges · depth ·
> amount · jurisdictions · patterns). **Temporal DAG canvas** — the
> centrepiece: X axis = time (window-start → end), Y axis = hop depth
> from seed, circles = accounts sized by amount and ringed by
> suspicion + role (funnel · mule · layer · integration), edges =
> animated dashed bézier curves with thickness ∝ amount and colour by
> pattern tag (rose for round-trip, orange for smurf, gold for
> pass-through, violet for integration, sky for geo-hop). Click any
> node → opens the **provenance drawer** with role chips, inflow /
> outflow / retention stats, active range, and the FIFO-traced
> source-attribution bars (each bar clickable to drill into that
> upstream account). **Pattern panel** ranks every detected pattern
> with confidence + evidence chips + recommended action + contributing
> node pills. **Trail-score breakdown** explains the composite as
> five labelled bars. **Plan-of-action** numbered list deep-links into
> the next TITAN tab. All deterministic — same `(transactions, seed,
> direction, depth, window)` in → identical bytes out, identical
> coordinates, identical bar widths. Engine: `titan-lineage/1.0.0`.

> **Day-60 — Pulse · the compliance officer's morning brief.** Every
> prior surface in TITAN measures *right now*: `risk` & `typology` score
> one batch, `profile` composites a customer's surfaces into one number,
> `cases` queues alerts, `peer` scores cohort outliers. None answer the
> question an MLRO opens Monday with — *"across my whole customer book,
> what's different since yesterday, and what should I look at FIRST?"*.
> New `apps/ai-aml/pulse.py` (~700 LOC, pure-stdlib, **zero new physics**
> — Pulse is a *composer*) reads every customer's persisted CRP + its
> history rows, the case-store's open cases + SLA breaches, derives a
> signed `composite_delta`, a `bucket_shift` (`medium → critical`), and
> a per-customer **signal** = `abs(Δ)·1 + bucket_upgraded·8 +
> new_case_critical·6 + new_case_high·4 + open_breach·5 + refresh_overdue·3
> + critical_floor·4`. A first-match-wins **mood ladder** (calm · watch ·
> active · critical) rolls the portfolio up; a **headline** names the
> biggest mover; a ranked **change-log** drops the top-10 plain-English
> deltas; a prioritised **plan-of-day** writes the analyst's first 8
> moves and *names the TITAN tab each one lives in* (Cases, Profile,
> Sanctions, Media). Ships a `titan.pulse.v1` JSON envelope + a
> paste-able markdown brief via `GET /aml/pulse/export.md`. **Surface**
> — new `/pulse` route between Overview and Profile: hero card with a
> mood-tinted breathing conic-gradient ring + ECG heartbeat polyline
> glyph + headline + advisory; 6-tile vital-signs strip (new cases · open
> · breaches · movers · KYC overdue · portfolio); SVG daily-activity
> sparkline with breach overlay; bucket-drift bars showing window-start
> vs now with dotted prior + solid now overlay; horizontally-scrolling
> Biggest Movers cards (per-customer composite ring + Δ-chip + bucket-shift
> chip + 2-line change excerpt, click → Profile); ranked Change Log + Plan
> of Day side-by-side; full customer roster table sortable by signal /
> composite / Δ with bucket pills + KYC status + breach chips + new-case
> markers; composite-distribution histogram tiered to the bucket palette;
> rules-explainer footer. Deterministic — same `(profiles, cases, now,
> window_days)` in → identical bytes out. The rotation deliberately ships
> Pulse across three projects in a row (WaySafe Day 56 → SynapseOS Day 59
> → TITAN Day 60): same vital-signs metaphor, different domains.

> **Day-30 — Typology Classifier.** Eight detectors answer
> *"what suspicious patterns are present?"*. Compliance officers always
> ask the next question: *"…and which playbook does that add up to?"*.
> The new `apps/ai-aml/typology.py` engine layers six FATF /
> Wolfsberg-style laundering typologies on top of the existing detector
> intensities + structural signals, returns a confidence per match,
> ranked evidence chips, an auto-generated narrative ready for the SAR,
> and a `severity_floor` that promotes the case priority when the
> playbook demands it (a `SANCEV` match forces critical even on
> otherwise-quiet accounts).
>
> | Code | Playbook | Drives priority to ≥ |
> |---|---|---|
> | `SMURF`  | Smurfing / structuring (sub-threshold deposit clusters → funnel) | high |
> | `LAYER`  | Layering through closed flow cycles | high |
> | `TBML`   | Trade-based ML (cross-border + diversity + round figures) | high |
> | `MULE`   | Mule-network pass-through (high fan-in + fan-out + low retention) | medium |
> | `SANCEV` | Sanctions evasion (watchlist alias + structural cover) | critical |
> | `INTEG`  | Integration (round-figure flows from a small set of sources) | medium |
>
> Every typology publishes a stable `code`, an accent colour, a 0..1
> `confidence` (sum of contributor weights × normalised signals ÷ max
> possible), ranked `evidence` chips with their per-contributor share,
> and a recommended action. The full library is dumped at
> `GET /aml/typologies` so auditors can verify the formula matches the
> definitions before the engine ships.
>
> **Surfaces.** When a case is opened the top typology is mirrored onto
> the case row (`typology_code`, `typology_confidence`), a
> `typology_assigned` event lands in the timeline, the snapshot grows
> a ranked list for the case-detail `TypologyPanel`, and the SAR
> generator leads the narrative with the playbook's auto-generated
> paragraph + the recommended action. The AML console renders a
> `TypologyBadge` chip on every alerted row and a full `TypologyPanel`
> in the detail drawer. Case queue cards show a typology chip next to
> the priority dot so the analyst sees the playbook at the swim-lane
> level. All deterministic — same factor intensities → same typology
> ranking, every time.

> **Day-35 — Model Validation.** Every other surface *measures* one
> batch. None answered the question a model-risk reviewer (SR 11-7 /
> FFIEC) asks first: *is the detection model any good?* A rule set that
> flags everyone has perfect recall and is useless; one that flags
> no-one is "accurate" on a low base-rate book and equally useless. The
> new `apps/ai-aml/backtest.py` engine replays the scorer against a
> **labelled** set of confirmed outcomes and reads the trade-off:
> the full confusion matrix at every threshold 0–100, precision /
> recall / Fβ / alert-rate curves, rank-based **ROC AUC** and average
> precision, an **Fβ-optimal recommended cut** (β=2 by default — a
> missed launderer costs far more than an extra review), and a
> **per-detector discrimination** table (each rule's own AUC over the
> positive vs negative population — which rules carry the signal, which
> are noise). It honours a candidate `weights` override, so a tuning
> hypothesis from the what-if simulator can be *validated*, not just
> admired. New `/validation` console: verdict banner, six headline
> tiles (with Δ-vs-canonical when you tune), an interactive
> confusion-matrix + ROC + metric-sweep you can scrub, ranked detector
> bars, and the scored-account ledger with per-row outcome chips. Pure
> function of `(transactions, labels, weights)` — admissible as model
> evidence.

> **Day-55 — Peer Lens.** Every other engine in TITAN measures one
> customer in isolation: `risk.py` fires deterministic rules per
> account, `drift.py` catches *account-vs-self* change, `profile.py`
> composites that customer's surfaces into one number, `network.py`
> propagates risk across the graph — but every input is still a
> *single-subject* signal. None of them ask the question regulators
> specifically ask in every exam: **"is this customer behaving
> differently from their *peers*?"** Peer-group benchmarking is
> explicitly required by the FFIEC BSA/AML exam manual ("Risk
> Identification Process"), MAS AML/CFT Notice 626 §8.1 ("customer
> due diligence including comparison against the customer's peer
> group"), and EU 6AMLD CDD guidance. A customer can sit safely
> *inside* their own historical envelope (drift-stable) and still be a
> textbook outlier vs their cohort.
>
> The new `apps/ai-aml/peer.py` engine (~620 LOC, pure-stdlib,
> deterministic) closes that gap. For every customer in a portfolio it
> extracts a **9-axis behavioral vector** from the last 30 days of
> transactions (`tx_count_30d · tx_volume_30d · avg_tx_amount ·
> p95_tx_amount · unique_counterparties · cross_border_pct · cash_pct ·
> weekend_pct · night_pct`), groups customers into **cohorts with
> hierarchical fallback** so every customer ends up in a peer group of
> at least 5 — `(industry × domicile × size_band) → (industry ×
> domicile) → (industry) → global` — and computes per-metric **robust
> z-scores using MAD**:
>
> ```
> z = 0.6745 · (x − median) / mad     if mad > 0
> z = (x − mean) / std                fallback when mad collapses
> z = 0                               flat cohort
> ```
>
> The `0.6745` constant scales MAD to a consistent estimator of σ for
> normally-distributed data, so `|z| ≥ 3` carries the same "3-sigma"
> intuition as a parametric z-score but is *resistant to contamination*
> by other outliers in the same cohort — the whole point of using a
> robust statistic on a portfolio where you *expect* a handful of bad
> actors. Each metric has a **directional gate** (`high-only` for
> volume / cross-border / cash / weekend / night — only *abnormally
> high* is suspicious; `both` for tx_count / unique_counterparties —
> abnormally low can mean off-book activity) so a wealth client who is
> simply tidy doesn't trip on a low cash share.
>
> Composite **outlier score** per customer:
>
> ```
> outlier = min(100, 10·max(|gated z|) + 5·count(|z| > 3))
> ```
>
> Saturating at 100 so one extreme axis (max_z=10 → 100) and broad
> misalignment (5 of 9 axes beyond 3σ → 25 from the extreme bumps, plus
> the max contribution) both reach the ceiling. Bands track the rest of
> TITAN: `aligned <25 · drifting 25..49 · outlier 50..74 · severe ≥75`.
> Every customer report carries the cohort it was scored against
> (with the explicit *level* used — `full`/`medium`/`loose`/`global` —
> so auditors can read "scored against industry|domicile (n=10)" off
> the response), the top 3 contributing metrics, the cohort
> distribution at that point (median, MAD, p25, p75, min, max), and a
> one-sentence headline a compliance officer can paste into a case
> note.
>
> Bundled **6-cohort demo portfolio** (`apps/ai-aml/data/peer_portfolio.json`)
> — 54 customers spanning Singapore export/import, Indian retail,
> Bahamian VASPs, Swiss wealth-mgmt, Dubai real estate, and German
> manufacturing — with a *planted outlier* in each cohort (cash-heavy
> exporter, structuring-pattern retail walk-in, high-volume VASP with
> KP/RU cross-border share, low-count wealth client with 4 wires of
> $4.7M each, cash-heavy real estate with single-counterparty
> concentration). Every planted outlier lands at `severe` on first run.
>
> The `/peer` console renders the result in a two-panel layout: a
> portfolio rail on the left with bucket + cohort chips, search, and
> ranked customer rows (each showing the score, bucket pill, cohort
> metadata, and the headline driver); a customer detail panel on the
> right with the conic-gradient outlier ring, recommended action card,
> top-3 driver tiles, and **per-metric peer-positioning bars** — every
> metric drawn as a horizontal range with the cohort's full min..max
> envelope, the IQR shaded in the metric's accent colour, the median
> tick, and the customer's value rendered as a haloed marker that sits
> exactly where they fall along the distribution. A collapsible engine
> rules card at the bottom shows the cohort fallback chain, the score
> composition, and the metric × direction list — every knob exposed for
> audit. Pure function of `(customers, transactions)`; the analysis
> re-runs in well under 100 ms on the 54-customer fixture.
>
> **Endpoints:**
> `GET  /aml/peer/rules` — metric list, direction gates, cohort fallback chain, score composition;
> `GET  /aml/peer/sample` — bundled six-cohort demo portfolio;
> `POST /aml/peer/analyze` — `{customers, transactions}` → portfolio rollup + cohorts + per-customer reports with full peer-positioning evidence.

> **Day-50 — Customer Risk Profile.** Every other surface in this repo
> measures *one* axis. Compliance teams are required by FATF Rec. 10
> (CDD / risk-based approach), EU 6AMLD, and BSA/FFIEC to maintain a
> **composite, customer-level** risk rating that drives KYC refresh
> cadence, product gating, and the regulator-facing book summary. That
> is the layer day-50 ships. The new `apps/ai-aml/profile.py` engine
> (~1000 LOC, pure-stdlib, deterministic) folds the six risk surfaces —
> AML transaction risk, sanctions exposure, adverse media, typology
> assignment, behavioural drift, network exposure — into one composite
> 0..100 per customer:
>
> ```
> composite = clip(
>     0.28·transaction_intensity      (from /aml/score · max(account.risk_score)/100)
>   + 0.22·sanctions_intensity        (max similarity scaled across the hit floor)
>   + 0.16·media_intensity            (composite from /aml/media/screen · /100)
>   + 0.12·typology_intensity         (top match confidence × severity multiplier)
>   + 0.12·drift_intensity            (overall drift from /aml/drift)
>   + 0.10·network_lift               ((network_risk − solo_risk) / 40, capped)
>   + geo_modifier                    (+5 if domicile ∈ FATF grey/black)
>   + pep_modifier                    (+8 if politically exposed)
>   + product_modifier                (+4 per high-risk product line, capped +12)
> , 0, 100)
> ```
>
> Modifiers cap at +20 total so no single bump can dominate. Buckets are
> FATF-aligned with refresh cadences baked in: `low <30 → 720d ·
> medium 30..59 → 365d · high 60..79 → 180d · critical ≥80 → 90d`.
> The refresh status is now-relative: `current · due_soon (within 30d) ·
> overdue`. Each profile carries an auto-generated executive narrative
> (dominant signal, modifier rationale, bucket-appropriate action), the
> per-surface evidence trail (top accounts · best alias · headline
> article · playbook code · onset date · network lift), and a
> SQLite-backed append-only **profile history** that captures every
> refresh, override, and clear-override with actor + before/after
> composite + bucket.
>
> The **analyst override** is the audit-grade part regulators inspect
> first: a senior analyst can pin a customer to a specific bucket with a
> justification (4..600 chars). The override is logged immutably; the
> *engine* composite is preserved alongside the *surfaced* override so
> reviewers see both numbers. Clearing the override emits a separate
> event on the same trail. Expired overrides (when the analyst sets an
> expiry ISO) lapse automatically on next refresh.
>
> Bundled 12-customer **demo book** (`apps/ai-aml/data/customers.json`)
> spans all four buckets — overlapping deliberately with the sanctions +
> adverse-media corpora so a single click lights the demo end-to-end
> (Trident Exports, Aurelia Shell, Crescent Maritime, Pyongyang Horizon,
> Volkov-Baranov). The `/profile` console mounts a portfolio rail with
> bucket + refresh chips + search, a customer-detail view (composite
> ring with engine-composite hint when an override is active, 6-axis
> `FactorWheel` polar fingerprint, per-surface evidence cards, an
> append-only history sparkline with bucket-band guides and override
> halos, an analyst-override dialog), and a portfolio-overview tab with
> bucket-share + refresh-state + domicile + top-of-book panels. Pure
> function of `(customer, evidence)` for the composite; the SQLite store
> is the only mutable surface and lives at
> `apps/ai-aml/data/profiles.sqlite3` (gitignored, per-deployment, WAL).
>
> **Endpoints:**
> `GET  /aml/profile/rules` — weights, buckets, refresh cadence, modifier knobs;
> `GET  /aml/profile/sample` — bundled customer book;
> `POST /aml/profile/seed` — persist the bundled book (idempotent unless `force=true`);
> `POST /aml/profile/compute` — one-shot composite from caller-supplied evidence (or transactions);
> `POST /aml/profile/refresh` — compute + persist + history entry;
> `GET  /aml/profile/portfolio` — filter by bucket / refresh / domicile / q + portfolio stats;
> `GET  /aml/profile/{customer_id}` — persisted profile + last 64 history rows;
> `POST /aml/profile/{customer_id}/override` — analyst override with required justification;
> `POST /aml/profile/{customer_id}/clear_override` — revert override (still logged).

> **Day-45 — Adverse Media OSINT.** Sanctions screening answers a
> *binary* question against a *closed* watchlist. Real EDD asks the
> open-world question that compliance teams use to escalate KYC
> reviews even without an SDN hit: *what is the world saying about
> this entity?* The new `apps/ai-aml/media.py` engine ships a
> deterministic, dependency-free **adverse-media screener** over a
> bundled 40-article corpus (`data/adverse_media.json`) that scores
> every party-name in a transaction batch — subject + counterparty —
> against an 11-category × 3-tier taxonomy. Per-article hit strength
> blends four signals that any auditor can recompute by hand:
>
> ```
> hit_strength = name_similarity        (0..1, fuzzy match)
>              * category_severity      (0..1, money_laundering=1.00 … litigation=0.50)
>              * source_tier_weight     (0..1, tier-1=1.00, tier-2=0.75, tier-3=0.50)
>              * recency_decay          (0..1, 0.5^(age_days / half_life_days))
> ```
>
> Per-entity composite is a saturating curve
> `100·(1 − exp(−Σ top_k(hit_strength) / 2.5))` bucketed into
> `clear · elevated · material · severe`, so one strong recent hit
> lands ≈ 29, four ≈ 73, ten saturate near 96. Name matching reuses
> the same token-set + char-3gram + containment blend as sanctions
> screening — only the floor is relaxed (0.55 vs 0.65) because media
> coverage is fuzzier than a SDN list. The new **`adverse_media`
> detector** is wired into the risk engine at weight 14, ramps
> linearly across composite 35–85, and ships evidence pointing at the
> top three articles. New `/media` console: hero with corpus stats +
> half-life knob, two tabs — `Screen entities` (left rail with names
> textarea + similarity floor / half-life sliders + presets;
> per-entity result cards with `MediaScoreRing`, category rollup
> bars, 4-bucket recency histogram, expandable article cards showing
> the per-hit similarity × severity × tier × recency breakdown and
> the matched mention) and `Browse corpus` (category + tier filter
> chips + search + an article grid). AML console now surfaces a
> `media · <composite>` chip on any account whose adverse-media grade
> hits `material` or `severe`, and the case snapshot carries the
> rollup so the case-detail surface inherits it. Pure function of
> `(names, similarity_floor, half_life)`, no ML deps.
>
> **Endpoints:**
> `GET  /aml/media/rules` — corpus metadata + tunable knobs;
> `POST /aml/media/screen` — batch entity screen with composite + grade + hits;
> `GET  /aml/media/articles` — browse the corpus (`category`, `tier`, `q`, `limit`);
> `GET  /aml/media/articles/{id}` — single article with severity / tier weights.

> **Day-40 — Behavioral Drift.** The eight rule detectors catch
> *threshold breaches* — a single transaction (or recent batch)
> crossed a line. They cannot catch the other half of laundering:
> **accounts whose recent behavior no longer matches their own
> historical baseline**. Sleeper takeovers, mule recruitments, slow
> operator shifts — the line itself moved, no single transaction
> crossed it. The new `apps/ai-aml/drift.py` engine measures that
> directly. For each account it splits transactions into a
> **baseline** and **current** window (either by fraction or an
> explicit ISO split timestamp) and compares the two along ten
> distribution-distance axes — amount distribution (Kolmogorov-
> Smirnov), hour-of-day & day-of-week histograms (Jensen-Shannon
> divergence), inflow/outflow balance, transaction velocity,
> counterparty concentration (Herfindahl) and **counterparty
> novelty** (the % of recent counterparties never seen in the
> baseline), geographic mix (total variation distance),
> round-amount tendency, and median ticket shift. Each axis
> produces a 0..1 sub-score; the composite is a fixed weighted
> sum bucketed into a verdict: `stable · mild · drifting ·
> erratic · transformed`. A rolling-window KS over the current
> window estimates a **change-point** (the earliest day the trailing
> 7-day slice crossed the floor). New `/drift` console: verdict-
> tinted hero ring + plain-English narrative + 10-axis polar
> fingerprint (baseline outer rim, drift dents inward) + per-
> dimension breakdown with weight×contribution bars + baseline-vs-
> current hour/day-of-week overlays + rolling-KS timeline +
> counterparty contribution table flagging new entrants and
> sudden-activity spikes. Pure function of
> `(transactions, split)`, no ML deps.

---

## What it does

| Stage | Endpoint | Notes |
|---|---|---|
| **Customer profile rules** | `GET  /aml/profile/rules` | Auditor view of CRP weights, buckets, refresh cadence, modifier knobs |
| **Customer book sample** | `GET  /aml/profile/sample` | Bundled 12-customer demo book spanning every bucket |
| **Seed sample book** | `POST /aml/profile/seed` | Persist the bundled book into SQLite (idempotent; `force=true` re-seeds) |
| **Compute profile** | `POST /aml/profile/compute` | One-shot composite from caller-supplied evidence (or transactions) |
| **Refresh profile** | `POST /aml/profile/refresh` | Compute + persist + history entry |
| **Portfolio listing** | `GET  /aml/profile/portfolio` | Filter by bucket / refresh / domicile / q + portfolio stats |
| **Get profile** | `GET  /aml/profile/{customer_id}` | Persisted profile + last 64 history rows |
| **Set override** | `POST /aml/profile/{customer_id}/override` | Analyst override with justification (audit-trailed) |
| **Clear override** | `POST /aml/profile/{customer_id}/clear_override` | Revert override (logged separately) |
| KYC ingest | `POST /kyc/verify` | PDF → SHA-256 → IPFS pin (Kubo) → on-chain attest |
| Attestation lookup | `GET  /attest/{docHash}` | Reads `AttestationRegistry.attestations[hash]` |
| Recent attestations | `GET  /attestations/recent` | Replays `Attested` events for the explorer feed |
| AML score | `POST /aml/score` | 9 detectors → 0..100 risk per account; accepts `weights` override |
| AML rules | `GET  /aml/rules` | Auditor-facing dump of weights / thresholds / watchlist + adverse-media meta |
| SAR draft | `POST /aml/sar` | Markdown narrative + structured payload |
| Sanctions screen | `POST /aml/sanctions/screen` | Fuzzy-match a batch of names against the watchlist |
| Sanctions list | `GET  /aml/sanctions/list` | Paged dump of bundled watchlist entries |
| **Adverse-media rules** | `GET  /aml/media/rules` | Auditor view of the corpus (size · categories · tiers · year coverage) + engine knobs |
| **Adverse-media screen** | `POST /aml/media/screen` | Batch-screen party names against the corpus → composite + grade + per-article hits |
| **Adverse-media browse** | `GET  /aml/media/articles` | Filter the corpus by `category`, `tier`, full-text `q` |
| **Adverse-media article** | `GET  /aml/media/articles/{id}` | One article with severity / tier weights |
| **Case queue** | `GET  /aml/cases` | Filter by status/priority/assignee/SLA/q |
| **Open case** | `POST /aml/cases/open` | Promote one `account_report` snapshot |
| **Bulk open** | `POST /aml/cases/bulk_open` | Promote a `/aml/score` response in one call |
| **Case stats** | `GET  /aml/cases/stats` | Tiles: open · breaches · per-status · avg-age |
| **Assignees** | `GET  /aml/cases/assignees` | Distinct list for the filter dropdown |
| **Case detail** | `GET  /aml/cases/{id}` | Snapshot + full event timeline |
| **Transition** | `POST /aml/cases/{id}/transition` | `to_status: review/cleared/escalated/sar_filed/reopen` |
| **Assign** | `POST /aml/cases/{id}/assign` | Set or clear analyst handle |
| **Note** | `POST /aml/cases/{id}/note` | Append a free-text note to the timeline |
| **File SAR** | `POST /aml/cases/{id}/sar` | Render SAR + attach + transition to `sar_filed` |
| **Delete** | `DELETE /aml/cases/{id}` | Hard delete (admin demo only) |
| **Network rules** | `GET  /aml/network/rules` | Entity-resolution + propagation thresholds |
| **Network analyse** | `POST /aml/network/analyze` | Cluster entities + propagate risk + return graph + layout |
| **Network counterfactual** | `POST /aml/network/counterfactual` | Ablate entities, rescore, return per-entity deltas |
| **Network attribution** | `POST /aml/network/attribution` | Leave-one-counterparty-out lift per account |
| **Case network panel** | `GET  /aml/cases/{id}/network` | Auto-runs entity resolution + propagation + member-aware attribution + "if cleared" deltas against the case's snapshotted neighbourhood |
| **Case network clearing** | `POST /aml/cases/{id}/network/clearing` | Override path — runs the case panel against caller-supplied transactions (for the AML console when no snapshot exists) |
| **Typology library** | `GET  /aml/typologies` | Auditor-facing dump of the six laundering typologies + per-contributor weights + confidence formula |
| **Typology classify** | `POST /aml/typologies/classify` | Re-classify one account report on demand — used by the what-if simulator after a weights override has reshuffled the factors |
| **Backtest sample** | `GET  /aml/backtest/sample` | Bundled labelled validation set (43 txs, 8 confirmed-bad across 5 typologies + 2 hard cases) for the one-click demo |
| **Backtest** | `POST /aml/backtest` | Replay the engine against labelled outcomes → confusion matrix · threshold sweep · ROC AUC · average precision · Fβ-recommended cut · per-detector discrimination · tuning verdict; honours a candidate `weights` override |
| **Drift rules** | `GET  /aml/drift/rules` | Auditor view of the drift engine's 10 weights, 5 verdict bands, change-point floor, and min-tx guards |
| **Drift sample** | `GET  /aml/drift/sample` | Bundled three-account demo (`ACC-STABLE`, `ACC-MILD`, `ACC-DRIFT` sleeper-burst) + a recommended ISO split timestamp |
| **Drift** | `POST /aml/drift` | Account-vs-self drift across ten axes (KS · JS · TVD · HHI · log-ratio) → verdict + driver ranking + change-point onset + per-counterparty contribution; portfolio mode ranks every eligible account |
| **Precedent rules** | `GET  /aml/precedent/rules` | Block weights + tunables + recommendation ladder for the case-similarity engine |
| **Precedent candidates** | `GET  /aml/precedent/candidates` | Open/review cases eligible as precedent queries |
| **Precedent for case** | `GET  /aml/precedent/case/{case_id}` | Top-k similar cases + block-attribution + Bayesian disposition prior + recommendation |
| **Precedent seed** | `POST /aml/precedent/seed` | Seed the case store with the six-family demo portfolio (idempotent unless `force=true`) |
| **Precedent export** | `GET  /aml/precedent/export.md` | Paste-able precedent memo for one case |
| **Triage rules** | `GET  /aml/triage/rules` | Signature-K + Laplace α + support gates + verdict ladder + detector list |
| **Triage profile** | `GET  /aml/triage/profile` | Portfolio prior + per-factor stats + 9x9 factor-pair suppression matrix + top noise/signal combos |
| **Triage candidates** | `GET  /aml/triage/candidates` | Open/review/escalated cases eligible for suppression scoring |
| **Triage for case** | `GET  /aml/triage/case/{case_id}` | Per-case Bayesian suppression report — scored combos, S score, verdict, cleared + SAR precedent chains |
| **Triage seed** | `POST /aml/triage/seed` | Seed the 12-family FP-rich supplementary corpus (idempotent unless `force=true`) |
| **Triage export** | `GET  /aml/triage/export.md` | Paste-able triage memo for one case (drops straight into a case note) |
| **Horizon rules** | `GET  /aml/horizon/rules` | Baseline weights + band cutoffs + every tunable + verdict ladder + preset library |
| **Horizon presets** | `GET  /aml/horizon/presets` | Six curated MLRO scenarios (OFAC uplift · Structuring hardening · FATF grey-list refresh · Noise reduction · New SDN additions · Band recalibration) with every knob resolved |
| **Horizon sample** | `GET  /aml/horizon/sample` | Bundled six-case demo — replays a preset (default: first) against six fixture accounts spanning the band spectrum. Everything the frontend needs to render the hero + waterfall + case grid is in the response. |
| **Horizon simulate** | `POST /aml/horizon/simulate` | Replay any proposal — over `fixture`, `store`, or caller-supplied `cases` — returns per-case delta + aggregate summary + waterfall + verdict. Deterministic: same input → same report. |
| **Horizon case** | `GET  /aml/horizon/case/{case_id}` | Per-case drill-down for a preset (`?preset=`). Returns impact + frozen snapshot + resolved proposal so the drill-down page renders an audit-quality explainer without extra round-trips. |
| **Horizon explain** | `POST /aml/horizon/explain` | Per-case drill-down for a caller-built proposal (weight-slider workflow). Same shape as `/case/{id}`. |
| **Horizon export** | `GET  /aml/horizon/export.md` | Paste-able impact memo — deterministic markdown for a change-management ticket. |
| **Nexus rules** | `GET  /aml/nexus/rules` | FinCEN CTA / OFAC / PEP thresholds + opacity component weights + jurisdiction-risk table + verdict ladder |
| **Nexus sample** | `GET  /aml/nexus/sample` | Bundled 29-entity / 24-edge portfolio: seven topologies exercising every branch (diamond just-below-UBO, OFAC cascade, hidden PEP, four-way clean split, five-layer shell chain, mutual-holding cycle, substantial-control officer) |
| **Nexus analyze** | `POST /aml/nexus/analyze` | Analyse a caller-supplied ownership graph — every target's UBO ladder, sanctions/PEP nexus, opacity, and verdict in one deterministic pass |
| **Nexus candidates** | `GET  /aml/nexus/candidates` | Every sanctioned / PEP / substantial-control natural person in the bundled corpus (picker for the reach view) |
| **Nexus entity** | `GET  /aml/nexus/entity/{id}` | Per-target UBO report, controllers with aggregate control, sanctions/PEP hits, opacity components, and cycles touching |
| **Nexus reach** | `GET  /aml/nexus/reach/{root_id}` | Downstream reach of a controller — every target with cumulative control + OFAC/PEP reach code |
| **Nexus export** | `GET  /aml/nexus/export.md` | Paste-able ownership memo — UBO table + sanctions/PEP nexus + top paths + opacity components + cycles |

The Next.js frontend at `:3000` is the human surface. It only talks to the
gateway at `:8000`, which fans out to `ai-ocr` (8001), `ai-aml` (8002), and
the Hardhat chain (8545).

---

## Risk engine, in detail

```
score(acct) = clip( Σ wᵢ · iᵢ(acct, txs, watchlist) , 0..100 )
```

| Detector | Weight | Fires when … |
|---|---:|---|
| `structuring`     | 24 | ≥3 transfers in `[40k, 50k)` within 24h (CTR-evasion proxy) |
| `velocity_spike`  | 14 | recent 1h volume ≥ 5× the trailing 30d baseline rate |
| `round_trip`      | 18 | a closed cycle of length ≤4 with every leg ≥ ₹50 000 |
| `sanctions_hit`   | 20 | subject or counterparty name matches the watchlist ≥ 65% similarity |
| `adverse_media`   | 14 | party-name composite in the adverse-media corpus ≥ 35 (intensity ramps to 1.0 at composite 85) |
| `fan_in`          |  7 | distinct senders ≥ 8 |
| `fan_out`         |  7 | distinct recipients ≥ 8 |
| `high_risk_geo`   |  6 | counterparty geo ∈ FATF-style watchlist |
| `round_amount`    |  4 | ≥3 transfers ≥ ₹100 000 that are perfect ₹10 000 multiples |

Each contribution is `intensity ∈ [0,1] × weight`. Intensity uses saturating
curves so the score plateaus instead of running away on pathological inputs.
Bands: `low <30 · medium <60 · high <80 · critical`.

`POST /aml/score` accepts an optional `weights` map — partial, per-detector
overrides clamped to `[0, 60]`. The response echoes `effective_weights` so
the frontend can render its **what-if simulator**: drag a slider, the
leaderboard reorders in ~250ms, and the response stays auditable because
the override travelled in the request body.

---

## Sanctions screening, in detail

```
similarity = 0.55 · token_set_ratio
           + 0.30 · char_3gram_overlap
           + 0.15 · containment           (substring either way)
           + 0.05 · jurisdiction_bonus    (post-blend, optional)
```

Each component is in `[0, 1]`; the blend stays in `[0, 1]`. The matcher
walks the canonical name *and* every alias and reports the strongest hit
together with the alias that produced it. Token-set is "soft-prefix"
aware so `volkov` matches `volkov-baranov` without overweighting
common-noun tokens — a stop-list strips legal-form suffixes (`Ltd`,
`GmbH`, `JSC`, `FZE`, etc.) before scoring.

| Grade | Range | Used for … |
|---|---:|---|
| `weak`   | 0.45 – 0.65 | Surfaced in `/watchlist` results, **not** an AML hit |
| `medium` | 0.65 – 0.80 | First grade that drives `sanctions_hit` to fire |
| `strong` | 0.80 – 0.92 | High-confidence alias match |
| `exact`  | ≥ 0.92 | Canonical-name match modulo punctuation/accents |

The bundled watchlist (`apps/ai-aml/data/sanctions.json`) ships 30
**illustrative** entries spanning OFAC SDN, UN-1267, UN-1718, EU-CFSP, and
UK-OFSI lists. Production deployments swap it via the `TITAN_WATCHLIST_PATH`
env var; the loader contract stays the same.

---

## Adverse-media OSINT, in detail

The `adverse_media` detector + `/media` console is a deterministic
open-source-intelligence layer. Sanctions screening answers a *binary*
question against a *closed* watchlist; adverse media answers the
**open-world** question that compliance teams use to escalate KYC
reviews even when no SDN hit exists — *what is the world saying about
this entity?*

### Composite formula

```
hit_strength = similarity                 (0..1, fuzzy name match)
              × category_severity         (0..1, money_laundering 1.00 … litigation 0.50)
              × source_tier_weight        (0..1, tier-1 1.00, tier-2 0.75, tier-3 0.50)
              × recency_decay             (0..1, 0.5 ^ (age_days / half_life_days))

raw       = Σ top_k (hit_strength)        (k default 12, saturates the long tail)
composite = 100 · (1 − exp(−raw / 2.5))   (saturating; 1 strong hit ≈ 29, 4 ≈ 73, 10 ≈ 96)
```

Name matching reuses the same physics as sanctions screening —
`0.55·token_set + 0.30·char_3gram + 0.15·containment` — only the floor
is relaxed (0.55 vs 0.65) because media coverage is fuzzier than a SDN
alias and false positives cost less than missing a real adverse hit.

### Grade bands

| Composite | Grade | UI hue |
|----------:|---|---|
| < 15      | `clear`    | teal |
| 15 – 39   | `elevated` | amber |
| 40 – 69   | `material` | orange |
| ≥ 70      | `severe`   | rose |

### How it lights up the AML score

The new `adverse_media` detector pulls every `subject_name` +
`counterparty_name` in the account's transactions, calls
`media.hits_for_account(names, similarity_floor=0.55)`, and converts
the rolled-up composite into a 0–1 intensity over the **35..85**
composite band. Intensity × `weight=14` = factor points. The detector's
evidence list points at the top three articles by hit-strength so the
case-detail surface can show the analyst exactly which articles drove
the alert.

### Corpus

The bundled corpus (`apps/ai-aml/data/adverse_media.json`) ships **40
illustrative articles** across **11 categories** and **3 source tiers**,
spanning 2023–2026 so the recency decay is exercised. Production
deployments plug in a licensed feed (Refinitiv World-Check, Dow Jones
Risk & Compliance, RDC, ComplyAdvantage) or a curated open-source
signal (FATF case studies, FinCEN enforcement actions, SEC press
releases) by overriding the loader path via
`TITAN_ADVERSE_MEDIA_PATH`; the loader contract stays the same.

### Frontend surface

The `/media` page is a two-tab analyst surface:

* **Screen entities** — names textarea on the left rail (with a
  similarity-floor slider, half-life slider + four presets:
  `90d · 180d · 1y · 2y`); per-entity result cards with a
  `MediaScoreRing` and category-strength chips; an expanded detail
  pane for the active name showing the composite ring, category
  rollup bars, a 4-bucket recency histogram (≤30d · ≤90d · ≤1y ·
  older), and the top hits as cards with their similarity × severity
  × tier × recency breakdown and the matched mention quoted back.
* **Browse corpus** — category + tier filter chips + full-text search
  + an article grid keyed by category accent.

AML console integration: any account whose adverse-media grade is
`material` or `severe` gets a `media · <composite>` chip on its row
(violet, click-through to `/media`); the run-summary tile strip grows
an **Adverse media** tile (count of accounts whose grade ≥ material);
the what-if simulator gets a 9th slider for the `adverse_media` weight.
The case-snapshot persists the adverse-media rollup so a re-opened
case sees the same evidence the analyst originally triaged.

---

## Case workflow, in detail

```
                          ┌───────────────┐
                          │  open  (auto) │
                          └───────┬───────┘
       ┌──────────────────────────┼──────────────────────────┐
       │                          ▼                          ▼
   ┌───────┐                 ┌─────────┐                ┌──────────┐
   │review │ ──────────────▶ │escalated│ ─────────────▶ │ sar_filed│ ◀── terminal
   └───┬───┘                 └────┬────┘                └────┬─────┘
       │                          │                          │
       └────────── cleared ◀──────┘                          │
                                                             ▼ reopen → review
```

**Priority** is computed once at open-time and re-validated on transition:

```
alert_score(case) = max( risk_score, max_similarity(sanctions) · 100 )
priority(case)    = critical  if alert_score ≥ 80
                    high      if alert_score ≥ 60
                    medium    if alert_score ≥ 30
                    low       otherwise
```

The `sanctions·100` axis means a strong alias match (similarity ≥ 0.85)
forces critical even on otherwise quiet accounts — exactly the inversion
real compliance teams expect.

**SLA** is a derived property of the open case (clock pauses on closure):

| State    | Threshold (default)   | Visual |
|----------|-----------------------|--------|
| `ok`     | < 24 h since opened   | teal pill |
| `warn`   | 24 h – 72 h           | amber pill |
| `breach` | ≥ 72 h                | rose pill |

Override per deployment with `TITAN_CASE_SLA_WARN_HOURS` /
`TITAN_CASE_SLA_BREACH_HOURS`.

**Audit trail.** The store is intentionally append-only on the
`case_events` side. Every transition, assignment, note, SAR generation,
and reopen emits a typed event with actor + before/after status + JSON
payload. The case detail timeline renders these chronologically with a
type-coloured rail (opened=teal, assigned=violet, note=slate,
status=amber, sar=emerald, reopened=orange).

**Idempotency.** Re-opening the same `account_id` within a calendar UTC
day returns the existing OPEN/REVIEW/ESCALATED case rather than creating
a duplicate. Closed cases re-open as fresh ones — the workflow resets.

**Snapshot persistence.** Every case stores a *frozen* snapshot of the
account report at triage time: factors with evidence, sanctions hits,
edges (capped at 64 rows), totals. Even if the underlying transactions
are re-classified later, the case detail still shows what the analyst
saw. That is the audit trail regulators care about.

---

## Network intelligence, in detail

Per-account scoring (`risk.py`) catches one account at a time. The new
`network.py` module catches the *picture* — three pieces, no ML:

### 1. Entity resolution

Two parties are merged via Union-Find if **either** of:

- **Name similarity ≥ 0.78** — reuses the watchlist matcher primitives.
  `combined = 0.55·token_set + 0.30·char_3gram + 0.15·containment` with
  the same `STOPWORDS` (legal-form suffixes like Ltd / GmbH / JSC stripped).
- **Counterparty-fingerprint Jaccard ≥ 0.55** (when both parties have at
  least 3 counterparties and share at least 3). Two hands that transact
  with substantially overlapping sets are likely the same hand.

Single-token names need an exact normalised match to merge, so `M1` and
`M2` won't collapse just because both names are short.

### 2. Risk propagation

A biased PageRank, on the row-stochastic money-flow adjacency:

```
r ← (1 − α) · s + α · Wᵀ · r           with α = 0.7
```

where `s` is the L1-normalised seed-risk vector (per-cluster max of the
contained account's `risk_score`), `W[i, j] = amount(i→j) / Σ amount(i→*)`,
and dangling rows teleport to `s`. Converges in ≤20 iterations on demo
data; we cap at 30 with `tol = 1e-5`. The final per-entity number is a
blend so per-account and neighborhood signals both show up:

```
network_risk = 0.55 · risk_score + 0.45 · 100 · (r / max(r))
```

A clean account heavily linked to a sanctioned one ends up amber, not
green — which is exactly the inversion this layer is meant to expose.

### 3. Counterfactual analysis

Ablate a set of entities, drop every transaction touching any of their
members, rerun risk.py + propagation, return per-entity deltas. The
answer to *"what if Entity-X were a mule and we cut them out — does the
rest of the picture clear?"* is now one click.

A complementary **attribution** call runs leave-one-counterparty-out on a
single account: for each partner, drop all transactions between the two,
rerun the scorer, report the score drop. This is the simplest possible
SHAP-style explanation — marginal contribution under a leave-one-out
coalition, deterministic, fully auditable.

### Layout

A deterministic Fruchterman-Reingold variant runs server-side and ships
coordinates with the response. The frontend renders SVG nodes at the
returned `(x, y)` immediately — no force-simulation flicker, no client
deps. SHA-seeded init keeps layouts stable across reloads but distinct
per dataset.

### Caps

The graph truncates at **80 nodes / 200 edges** ranked by sanctioned
status → risk_score → activity. Sanctioned nodes always make the cut so
a truncated view never silently drops the most important signal.

---

## Case-aware network panel, in detail

The case workflow (day-15) and the network engine (day-20) shipped as
two surfaces with no link between them. From day-25 the case detail
auto-runs the network engine against a **persisted neighbourhood
snapshot** of the transactions that triggered the alert, so the moment
an analyst opens a case they see the *picture*, not just the per-account
factors.

### Snapshot persistence

When a case is opened (one-off or bulk), the AML service slices the
1-hop neighbourhood around the subject:

- every transaction whose `account_id` or `counterparty` is the subject
- plus every transaction *between* the subject's direct counterparties
  (the induced subgraph over the subject + direct neighbours)

It persists that subset into a new `case_transactions(case_id PK, …)`
table — JSON column for the payload, scalar mirrors for `tx_count` and
`counterparty_count`, cap of `TITAN_CASE_TX_SNAPSHOT_CAP=1500` rows.
Most-recent-first truncation when over budget. Older callers that don't
attach transactions still open cases as before; the case panel just
shows an empty-state with a "re-promote with the source attached" hint.

### What the panel runs

```
GET /aml/cases/{id}/network?hops=1
```

1. Reads the snapshot.
2. Runs the standard `analyze(...)` on the subset — entity resolution
   (Union-Find on name similarity + counterparty Jaccard) + biased
   PageRank + deterministic FR layout.
3. Crops to a **22-node / 80-edge BFS subgraph** centred on the case's
   resolved entity (`CASE_PANEL_MAX_NODES` / `…_EDGES` in `network.py`).
   Edges over the cap are sorted by aggregate amount so the most
   material flows always survive.
4. Runs **member-aware attribution** — when the subject is a
   multi-member aggregate cluster, leave-one-counterparty-out runs
   across all members at once. The cluster baseline is `max(member
   scores)` (matches the seed-risk convention used in propagation), and
   each contribution reports the cluster-level drop. Internal
   member-to-member edges are kept constant (intra-cluster wiring isn't
   a counterparty).
5. Runs a **"clear this case" counterfactual** — ablate the subject's
   entire entity, rerun the pipeline, return:
   - `network_avg_before/after`
   - `alerted_before/after` (count of entities ≥60 network risk)
   - **`peer_lifts`** — the top-8 entities sorted by *most-negative*
     `network_delta`. These are the peers whose risk drops the most
     when the subject is removed: the answer to *"who depends on this
     account?"*

### Override path

If the case has no snapshot (legacy data, or the caller wants a
recompute against a different weights override), `POST
/aml/cases/{id}/network/clearing` runs the same pipeline against
caller-supplied transactions. The AML console uses it as a fallback
when the page renders a case that was opened before snapshots existed.

### Frontend

`CaseNetworkPanel.tsx` is mounted between the evidence snapshot and the
sanctions hits panel on every case detail page. It renders:

- 4 headline tiles (solo risk · network risk + lift caption · "if
  cleared" Δ avg · alerted-count flip + txs-removed caption)
- the BFS subgraph via the existing `RiskGraph` SVG (no new chart deps),
  centred on the subject
- per-member breakdown when the subject is aggregate
- counterparty attribution bars (amber = positive lift, teal = negative)
- peer-lifts list (teal-down chips for biggest peer drops)
- 0/1/2 hop segmented control + manual refresh + "open in full network →"
  deep-link

---

## Typology classifier, in detail

The classifier is a deterministic, declarative library. Each typology is
a `TypologyDef` with a tuple of `_Contributor` rows; each contributor is
either a detector key (e.g. `structuring`) or a derived structural
signal (e.g. `__retention__`). At classify time the engine walks the
account report's factor map, recovers each detector's `intensity =
points / weight ∈ [0, 1]`, computes derived signals from the structural
fields, multiplies through the per-contributor weights, sums, and
divides by the maximum attainable for that typology:

```
confidence(typology) = Σ ( signal_i × weight_i )  /  Σ weight_i
```

A perfect match scores `1.00`. Matches below `CONFIDENCE_FLOOR = 0.35`
are dropped so the SAR narrative never carries weak playbooks. The top
`MAX_REPORTED = 3` are returned.

### Contributor rows (the formula, made explicit)

| Typology | Contributors (weight) |
|---|---|
| `SMURF` | `structuring` 1.00 · `fan_in` 0.55 · `round_amount` 0.35 · `velocity_spike` 0.25 |
| `LAYER` | `round_trip` 1.00 · `velocity_spike` 0.40 · `round_amount` 0.30 · `high_risk_geo` 0.25 |
| `TBML`  | `high_risk_geo` 1.00 · `fan_out` 0.55 · `round_amount` 0.40 · `sanctions_hit` 0.35 |
| `MULE`  | `fan_in` 0.55 · `fan_out` 0.55 · `velocity_spike` 0.50 · `__retention__` 0.50 · `structuring` 0.20 |
| `SANCEV` | `sanctions_hit` 1.00 · `__sanctions_strength__` 0.55 · `high_risk_geo` 0.30 · `round_trip` 0.25 |
| `INTEG` | `round_amount` 1.00 · `__low_counterparty_density__` 0.55 · `velocity_spike` 0.30 · `high_risk_geo` 0.25 |

The three derived signals are:

- **`__retention__`** — `(1 − |in − out| / max(in, out))²`. Squared so
  near-symmetric flows score 1.0 (pass-through node, mule signature),
  and asymmetric ones (pure inbound aggregator) score 0.
- **`__sanctions_strength__`** — `(best_similarity − 0.65) / 0.35`,
  clipped to `[0, 1]`. A 0.65 (entry-threshold) match contributes 0;
  a 1.0 exact match contributes 1.0. Additive on top of the base
  `sanctions_hit` detector so we never double-count low matches.
- **`__low_counterparty_density__`** — `max(0, 1 − cp_count / 6)`.
  Three counterparties → 0.5; six → 0. Captures the
  "value concentrated in a handful of sources" signature of the
  integration stage.

### Priority promotion via `severity_floor`

Cases default to a priority derived from
`max(risk_score, sanctions_pct)`. When a critical-floor typology like
`SANCEV` fires, the case rides at critical even when the per-account
score sits in the 60s — this is the inversion compliance teams expect.
The promotion is logged in the `opened` event payload's
`promoted_by_typology: true` flag so the audit trail captures both the
base reasoning and the override.

### Storage

Two idempotent SQLite migrations land on first boot:

- `ALTER TABLE cases ADD COLUMN typology_code TEXT`
- `ALTER TABLE cases ADD COLUMN typology_confidence REAL`

Both are introspected via `PRAGMA table_info(cases)` so the migration
re-runs cleanly against any version of the schema. The ranked list of
runners-up rides on the existing snapshot JSON (no separate table) —
the snapshot is already the system-of-record for the account-report
shape, so we don't fragment storage. A new `typology_assigned`
case-event type carries `{code, name, confidence, severity_floor,
evidence, runners_up}` for the timeline.

### SAR narrative

`render_sar()` reads `account_report.typologies` and adds a new §3
"Laundering typology" block above the per-detector bullets. The block
contains: the primary typology + code + confidence + severity floor,
the auto-generated narrative paragraph (interpolated from the live
account stats — totals, counterparty count, the structuring/cycle/geo
detail strings lifted off the firing detector), ranked contributing
evidence with signal percentages, and the per-typology `recommended_action`
that pre-fills §5. Runners-up are listed as chips at the bottom of the
block so the analyst can switch playbooks before finalising.

### Example: SMURF case in flight

```bash
curl -s :8000/aml/typologies | jq '.typologies | map(.code)'
# ["SMURF","LAYER","TBML","MULE","SANCEV","INTEG"]

# Score 12 sub-threshold transfers from A1 across 9 recipients
curl -s :8000/aml/score -H 'Content-Type: application/json' \
     -d @demo_smurf.json | jq '.accounts[] | select(.account_id=="A1")
                               | {risk_score, typology: .typologies[0]}'
# {
#   "risk_score": 47,
#   "typology": {
#     "code": "SMURF",
#     "name": "Smurfing / Structuring",
#     "confidence": 0.581,
#     "severity_floor": "high",
#     "evidence": [
#       { "label": "Sub-threshold deposit clusters", "signal": 1.000, ... },
#       { "label": "Burst in inbound velocity",      "signal": 1.000, ... }
#     ]
#   }
# }

# Open the case — top typology mirrored onto the row, event in timeline
curl -s -X POST :8000/aml/cases/open \
     -H 'Content-Type: application/json' \
     -d '{"account_report": <a1_above>}' | jq '.case | {id, priority, typology_code, typology_confidence}'
# {"id":"CASE-...","priority":"high","typology_code":"SMURF","typology_confidence":0.581}
```

---

## Model validation / backtest, in detail

A scorer is only as good as its measured separation between
confirmed-bad and benign. `backtest.py` makes that measurable.

### Inputs

```
POST /aml/backtest
{ "transactions": [...],          // same shape as /aml/score
  "labels": ["A1","A2","MULE"],   // confirmed-suspicious ids, OR
                                  // {"A1":1,"N1":0,...} to restrict the
                                  // population to adjudicated accounts only
  "weights": { "fan_in": 30 },    // optional candidate tuning to validate
  "beta": 2.0,                    // Fβ recall-weighting (compliance default)
  "operating_threshold": 30 }     // the current case-open cut to benchmark
```

A plain id-list means *"these are known-bad; treat every other scored
party as good"* — the realistic confirmed-SAR setup. A dict labels both
classes and drops everything unlabelled, so you can validate against a
hand-adjudicated sample.

### What it computes

1. **Confusion matrix at every cut 0–100.** Predicted-positive when
   `risk_score ≥ τ`. From `(TP, FP, FN, TN)` it derives precision,
   recall, specificity, F1, Fβ, balanced accuracy, alert-rate and
   Youden's J at each τ.
2. **ROC AUC** — rank-based (Mann-Whitney U, ties at 0.5), computed
   exactly over all positive×negative pairs. `AUC = P(score(rand bad) >
   score(rand good))`. No sampling, no seed.
3. **Average precision** — step-wise area under the PR curve over the
   sweep, robust to a non-monotone curve.
4. **Recommended operating point** — the τ that maximises Fβ (ties broken
   toward higher recall, then lower alert burden). `β = 2` weights recall
   2× precision because the cost of a missed launderer dominates.
5. **Per-detector discrimination** — for each of the eight detectors, its
   *own* single-feature AUC over the positive vs negative intensity
   distributions. This is the part that pays for itself: it tells you
   which rules separate good from bad and which are near-random noise you
   can down-weight — closing the loop with the what-if simulator.
6. **Verdict** — a grade (`strong / fair / marginal / poor`) off the ROC
   AUC plus plain-English notes ("lowering the cut to 7 lifts recall from
   75% to 100%"; "low-signal detectors on this set: …"; "N known-bad
   accounts slip under the current cut").

### The loop it closes

The what-if simulator (day-1) lets you *re-weight* detectors and watch
the leaderboard move. Validation tells you whether that move was *good*.
On the bundled set the canonical rules score AUC 0.96 but the mule
pattern (fan-in + fan-out, weighted 8+8) scores under the case-open cut —
a recall miss. Boosting the fan weights recovers the mule at higher
precision than blindly lowering the threshold, and the headline tiles
show the Δ-vs-canonical to prove it. That is model tuning with evidence.

### Determinism

`backtest(transactions, labels, weights)` is a pure function — same
inputs → identical report, every time. No persisted state, no I/O, no
randomness. That is what makes a backtest admissible as model evidence.

---

## Behavioral drift, in detail

The risk engine asks *"did this transaction cross a line?"*. Drift asks
the opposite question: *"does this account still look like itself?"*.

Same account holder, same wallet, same KYC document. Months of routine
inflows from a single contact, mid-afternoon hours, ₹5k tickets. Then
the account starts firing ₹50k+ round-amount outflows at 3 AM to a
fresh set of counterparties in a different jurisdiction. Every single
one of those transactions sits below every per-transaction threshold —
no rule fires. But the account is no longer behaving like itself, and
that, in real AML, is the signal.

### Inputs

`POST /aml/drift` takes:

* `transactions[]` — the same `Tx` shape every other route accepts.
* `account_id?` — when present, the response is `scope: "single"`. When
  absent, the engine ranks **every** account that has enough
  transactions on both sides of the split.
* `baseline_fraction?` (default `0.7`) — fraction of the timeline that
  forms the baseline window.
* `split_at?` — explicit ISO timestamp. Overrides the fraction. Use
  this when an analyst already has a hypothesis about *when* drift
  started; the engine will validate it against the data.

### Ten axes

| Axis | Stat | Sub-score |
|---|---|---:|
| `amount`             | two-sample Kolmogorov-Smirnov on tx amounts | KS statistic |
| `hour`               | Jensen-Shannon divergence on 24-bucket hour-of-day | JS / ln 2 |
| `dow`                | Jensen-Shannon on 7-bucket day-of-week | JS / ln 2 |
| `direction`          | absolute delta in inflow / total ratio | scaled to 0..1 |
| `velocity`           | log-ratio of tx-per-active-day | abs(log) / log 5 |
| `cparty_diversity`   | absolute delta in Herfindahl-Hirschman of counterparty share | direct |
| `cparty_novelty`     | % of current counterparties never seen in baseline | direct |
| `geo`                | total-variation distance between geo-mix vectors | direct |
| `round_rate`         | abs delta in % of round-amount transfers | scaled to 0..1 |
| `median_shift`       | log₂ shift of median amount | abs(log₂) / 3 |

```
overall = clip(
    0.18·amount + 0.14·hour + 0.10·dow + 0.10·direction
  + 0.08·velocity + 0.08·cparty_diversity + 0.12·cparty_novelty
  + 0.08·geo + 0.05·round_rate + 0.07·median_shift,
  0, 1)
```

The weights sum to 1.0 and live in `apps/ai-aml/drift.py::WEIGHTS` —
they're dumped at `GET /aml/drift/rules` so auditors can verify them
before the engine ships.

### Verdict bands

| Composite | Verdict | Recommended action |
|---:|---|---|
| < 0.18 | `stable`      | no action — within tolerance |
| < 0.35 | `mild`        | monitor — schedule a routine review next cycle |
| < 0.55 | `drifting`    | review — flag for an analyst pass within 5 business days |
| < 0.75 | `erratic`     | escalate — promote to a case at medium priority |
| ≥ 0.75 | `transformed` | escalate — promote to a case at high priority and confirm account-holder identity |

### Change-point estimate

For every day in the current window we take the trailing 7-day slice of
recent activity and compute KS against the **full baseline**. The first
day above `change_point_ks_floor` (default `0.30`, configurable in
`/aml/drift/rules`) — with at least three transactions in the trailing
slice — is reported as the **drift onset**. The full rolling-KS series
ships with the response so the frontend renders a timeline with the
floor as a dashed line and the onset as a pulsing dot.

### Counterparty contribution

A small table per account: top 8 counterparties ranked with brand-new
ones first, then by current activity. Each row carries
`(baseline_count, current_count, baseline_volume, current_volume,
is_new, activity_lift, volume_lift)` so the analyst can spot *which*
counterparties are the source of the drift, not just *that* drift
happened.

### Bundled demo

`GET /aml/drift/sample` ships a deterministic three-account dataset
that exercises every verdict band:

* `ACC-STABLE` — six months of routine vendor transfers; landing
  verdict `stable`.
* `ACC-MILD` — same routine, gentle ticket growth; landing `mild`.
* `ACC-DRIFT` — eighteen weeks of small, mid-afternoon inflows from
  a single contact, then a nine-day burst of large round-amount
  outflows at 2–5 AM to three brand-new counterparties, half abroad.
  Landing `drifting` on the default fraction split and `transformed`
  (overall `0.84`) when split at the recommended ISO timestamp.

A single click loads the data + the recommended split timestamp into
the `/drift` console so a first-time visitor sees the full surface
populate immediately.

### Determinism

`drift.analyze(transactions, ...)` is a pure function. Same inputs →
identical report, every dimension score, every per-day KS value, every
narrative byte. That's the contract: a drift verdict has to be
defensible to a regulator the same way a rule-based alert is.

---

## Frontend

| Route | Purpose |
|---|---|
| `/` | Hero + 4-step pipeline + nine feature cards + flow diagram |
| `/peer` | **(new — day-55)** Peer Lens console: portfolio rail with bucket + cohort chips + search, ranked customer rows tagged with cohort metadata and the headline driver; right-panel customer detail with conic-gradient outlier ring, recommended-action card, top-3 driver tiles with z-scores, and **per-metric peer-positioning bars** — each metric drawn as a horizontal range with the cohort's min..max envelope, IQR shaded in the metric accent, median tick, and the customer's value rendered as a haloed marker exactly where they fall along the distribution. Collapsible engine-rules card at the bottom exposes the cohort fallback chain, score composition, and metric × direction list for audit |
| `/profile` | **(day-50)** Customer Risk Profile console: portfolio rail with bucket + refresh + search filters; customer detail with composite ring (engine-composite hint when overridden), 6-axis `FactorWheel` polar fingerprint, per-surface evidence cards, append-only history sparkline with bucket-band guides + override halos, and an analyst-override dialog; portfolio overview tab with bucket-share + refresh-state + domicile + top-of-book panels |
| `/aml` | Drag-drop CSV → ranked accounts, factor bars, transaction graph, sanctions hits, **what-if weight sliders**, SAR draft, case promotion (per-row chip and bulk header button), `Network →` deep-link, **+ inline typology badge on every alerted row** and a full `TypologyPanel` with confidence ring + ranked evidence bars + narrative + recommended-action in the detail drawer |
| `/network` | Resolved entities, risk-coloured force graph, sortable sidebar, counterfactual ablation panel, per-account attribution view |
| `/precedent` | **(new — day-70)** Case-precedent console: verdict-accent-tinted hero banner with recommendation label + rationale, 4-tile aggregate strip (precedent count · Laplace-smoothed P(SAR) · median time-to-resolve · corpus considered), searchable priority-tinted candidate picker (open/review queue, or include-closed for audit), Bayesian posterior bar with 50/50 base-rate reference and per-disposition counts, `k` precedent cards each rendering a conic similarity ring + disposition/band/typology chips + top firing factors + block-attribution driver bars + top-6 axis delta chips against the query, and a one-click "precedent memo" markdown export. Includes a "seed demo portfolio" affordance for fresh installs |
| `/drift` | **(new — day-40)** Behavioral-drift console: verdict-tinted hero ring with plain-English narrative + recommended action, 10-axis polar fingerprint (baseline ring on the outer rim, drift dents inward), baseline-vs-current window cards, ranked per-dimension breakdown with score × weight × contribution bars, baseline-vs-current hour-of-day and day-of-week distribution overlays, rolling-KS change-point timeline with onset pulse, and counterparty contribution table flagging new entrants and sudden-activity spikes. Portfolio mode adds a 6-tile summary banner + a ranked left rail that swaps the active report on click |
| `/validation` | Model-validation console: verdict banner, six headline tiles (ROC AUC · avg precision · recommended cut · recall/alert-rate @ rec · base rate, each with Δ-vs-canonical when you tune), an interactive confusion matrix + ROC curve + scrubable metric-sweep (precision/recall/Fβ/alert-rate vs threshold), ranked per-detector discrimination bars, the scored-account ledger with per-row outcome chips, and a live weight-tuning panel that re-validates a hypothesis |
| `/cases` | Kanban-style queue: 6-tile stats banner, priority swim lanes (critical/high/medium), low-priority collapsed list, search + assignee + SLA filters, live nav badge |
| `/cases/{id}` | Big alert ring, priority/SLA pills, **typology badge in the header**, frozen evidence snapshot (factor bars + tx graph), **`TypologyPanel`** with full breakdown (confidence ring, ranked evidence bars, auto-narrative, recommended action), **network panel** auto-running entity resolution + propagation + member-aware attribution + "if cleared" deltas on the case's snapshot, sanctions hits panel, status workflow buttons, assignment widget, note composer, full **timeline** rail (now renders `typology_assigned` events with the badge), attached SAR with collapsible markdown view |
| `/watchlist` | Batch screening (paste names, set jurisdiction prior + similarity floor), per-query result cards with a `SimilarityRing` and component-level breakdown, plus a searchable browse view of the bundled watchlist |
| `/kyc` | PDF dropzone, animated 3-stage pipeline, on-chain receipt with deep-link to explorer |
| `/attestations` | Search by `docHash`, live `Attested` event feed, click-through to detail |

Built with Next.js 14 + Tailwind + a small set of inline SVG components
(`ScoreRing`, `SimilarityRing`, `FactorBars`, `TxGraph`, `PriorityDot`,
`AgePill`, `Timeline`, `CasesNavPill`, `RiskGraph`, `EntityCard`,
`DeltaBar`, `CaseNetworkPanel`, `TypologyBadge`, `TypologyPanel`,
`ConfusionMatrix`, `MetricSweep`, `RocCurve`). No charting libs.

---

## Quickstart

```bash
cd infra
cp env.example .env       # optional — defaults work for local
docker compose up --build
```

Services:

- Frontend: <http://localhost:3000>
- API gateway: <http://localhost:8000/docs>
- AML engine: <http://localhost:8002/docs>
- IPFS gateway: <http://localhost:8080>
- Hardhat node: <http://localhost:8545>

The Hardhat dev account
`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` is preloaded with funds; the
gateway uses the well-known dev private key to sign attestation transactions.
**Don't reuse that key outside local dev.**

---

## Sanity check (no Docker)

```bash
cd apps/ai-aml
pip install -r requirements.txt
uvicorn main:app --port 8002

# 1) score the bundled sample
curl -s -X POST localhost:8002/aml/score \
  -H 'Content-Type: application/json' \
  -d @../../datasets/samples/aml-sample.json | tee /tmp/score.json | head -20

# 2) bulk-promote alerts to cases
curl -s -X POST localhost:8002/aml/cases/bulk_open \
  -H 'Content-Type: application/json' \
  -d "{\"score_response\": $(cat /tmp/score.json), \"min_priority\": \"medium\"}" \
  | python -m json.tool | head -40

# 3) walk the queue
curl -s localhost:8002/aml/cases | python -m json.tool | head
curl -s localhost:8002/aml/cases/stats | python -m json.tool

# 4) drive a case through the workflow (replace CASE-XXX with a real id)
CID=CASE-XXXXXXXXXX
curl -s -X POST localhost:8002/aml/cases/$CID/assign \
  -H 'Content-Type: application/json' \
  -d '{"assignee":"alice","actor":"system"}'
curl -s -X POST localhost:8002/aml/cases/$CID/transition \
  -H 'Content-Type: application/json' \
  -d '{"to_status":"review","actor":"alice","note":"Triaging."}'
curl -s -X POST localhost:8002/aml/cases/$CID/sar \
  -H 'Content-Type: application/json' \
  -d '{"actor":"alice","analyst":"alice"}' | python -m json.tool | head -30

# 5) network intelligence — analyse → ablate → attribute
curl -s -X POST localhost:8002/aml/network/analyze \
  -H 'Content-Type: application/json' \
  -d @../../datasets/samples/aml-sample.json | python -m json.tool | head -40
curl -s -X POST localhost:8002/aml/network/counterfactual \
  -H 'Content-Type: application/json' \
  -d '{"transactions": [...], "ablate": ["B"]}' | python -m json.tool
curl -s -X POST localhost:8002/aml/network/attribution \
  -H 'Content-Type: application/json' \
  -d '{"transactions": [...], "account_id": "A2"}' | python -m json.tool
```

Or just open the **AML console** in the browser — drop the bundled CSV,
hit **Score**, hit **Network view →** to see the propagated graph, then
toggle the − button on any sidebar entity and **Re-score without N** to
run a counterfactual.

---

## Layout

```
apps/
  api/              FastAPI gateway — KYC ingest, attestation lookup, AML pass-through
  ai-ocr/           PAN PDF stub — sha256 + IPFS pin
  ai-aml/           Risk engine + sanctions matcher + SAR generator (no ML deps)
    risk.py             8 detectors + weight-override support + per-account typology classify
    sanctions.py        token-set + n-gram + containment matcher
    sar.py              markdown narrative + structured payload + auto-led typology §3
    typology.py         6 laundering typologies (SMURF · LAYER · TBML · MULE · SANCEV · INTEG)
                         · deterministic confidence scorer · severity-floor priority promotion
                         · auto-generated narrative + recommended action per match
    backtest.py         model validation — confusion sweep + ROC AUC + average precision
                         · Fβ-optimal recommended cut · per-detector discrimination (single-
                         feature AUC) · tuning verdict · bundled labelled validation set
    drift.py            behavioral drift — 10-axis account-vs-self engine (KS · JS · TVD ·
                         HHI · log-ratio) · 5-band verdict · rolling-KS change-point ·
                         per-counterparty contribution · auto-narrative · bundled
                         three-account demo (stable + mild + sleeper-burst)
    profile.py          Customer Risk Profile — 6-surface composite engine
                         (transaction · sanctions · media · typology · drift · network)
                         · FATF-aligned buckets + refresh cadence
                         · analyst-override + append-only history audit
                         · SQLite-backed portfolio + bundled 12-customer demo book
    peer.py             Peer Lens — peer-group statistical anomaly engine
                         (9 behavioural axes: tx_count · volume · avg · p95 ·
                          unique_cps · cross_border · cash · weekend · night)
                         · hierarchical cohort fallback (industry × domicile × size →
                            industry × domicile → industry → global)
                         · robust MAD z-scores (parametric std fallback)
                         · directional gating (high-only vs both per metric)
                         · saturating composite + 4-band verdict (aligned · drifting ·
                            outlier · severe)
                         · bundled 6-cohort, 54-customer demo portfolio with planted
                            outliers in each cohort
    cases.py            SQLite-backed case store + workflow engine + SLA
                         + typology_code/typology_confidence mirror columns
                         + typology_assigned timeline events
    network.py          entity resolution + biased PageRank + counterfactual + attribution
                         + case_panel(): one-shot per-case surface
                         + attribution_for_entity(): member-aware leave-one-out
    data/sanctions.json bundled illustrative watchlist
    data/cases.sqlite3  case + case_transactions persistence (gitignored, per-deployment)
  frontend/         Next.js 14 console (dark theme, glass UI)
    app/network/page.tsx        entity graph + counterfactual + attribution
    app/cases/page.tsx          queue: kanban + stats + filters
    app/cases/[id]/page.tsx     detail: timeline + evidence + workflow
    components/CaseCard.tsx
    components/CasesNavPill.tsx
    components/Timeline.tsx
    components/PriorityDot.tsx
    components/AgePill.tsx
    components/RiskGraph.tsx        force graph with risk-coloured nodes + arrows
    components/EntityCard.tsx       sidebar row with conic-gradient ring + ablate toggle
    components/DeltaBar.tsx         diverging-bar visualisation for signed deltas
    components/CaseNetworkPanel.tsx in-case network surface: subgraph + attribution + "if cleared" tiles
    components/TypologyBadge.tsx    icon + code + confidence ring chip (xs/sm/md)
    components/TypologyPanel.tsx    full breakdown: ring + ranked evidence + narrative + recommended action
    app/validation/page.tsx        model-validation console: verdict + tiles + sweep + ROC + detectors
    components/ConfusionMatrix.tsx  2×2 TP/FP/FN/TN grid, tone-coded by cost
    components/MetricSweep.tsx      P/R/Fβ/alert-rate vs threshold, scrubable cursor + guides
    components/RocCurve.tsx         ROC curve with shaded AUC + operating-point markers
    app/drift/page.tsx             behavioral-drift console: verdict hero + radar + per-dim
                                    bars + hour/dow overlays + KS timeline + cparty table
    components/DriftRadar.tsx       10-axis polar fingerprint (baseline rim, drift dents inward)
    components/DistributionOverlay.tsx baseline-vs-current normalised-histogram pair
    components/DriftTimeline.tsx    rolling-KS curve with onset pulse + threshold guide
    app/profile/page.tsx           Customer Risk Profile console — portfolio rail +
                                    customer detail + override dialog + portfolio overview
    components/ProfileRing.tsx      conic-gradient composite ring with engine-composite hint
    components/FactorWheel.tsx      6-axis polar fingerprint — weight rim + intensity polygon
    components/RefreshTimeline.tsx  KYC anchor → today → next-due rail tinted by refresh state
    components/HistoryStrip.tsx     composite sparkline with bucket-band guides + override halos
blockchain/
  contracts/        AttestationRegistry.sol
  scripts/          deploy.ts
infra/              docker-compose for the whole stack
datasets/           sample inputs
```

## Roadmap

- ~~**Phase 2** — sanctions feed (✅ shipped, day-10), DB persistence
  for cases & alerts (✅ shipped, day-15 — SQLite + workflow + timeline +
  SLA), ~~SHAP-style attributions on top of the rule engine~~ (✅ shipped,
  day-20 — leave-one-counterparty-out attribution + counterfactual ablation).~~
- **Phase 3** — Zero-knowledge attestation circuits (prove "I am attested
  by V" without revealing the docHash); GraphQL subgraph for the explorer;
  OAuth + analyst RBAC; live alerting / web-hooks on case state changes;
  ~~member-chooser for attribution on aggregate clusters~~ (✅ shipped,
  day-25 — `attribution_for_entity()` runs leave-one-out across all
  members of an aggregate cluster, with per-member baseline scores);
  ~~expose network intelligence as a case-detail panel (auto-run when a
  case is opened)~~ (✅ shipped, day-25 — `CaseNetworkPanel` mounts on
  every case detail and runs against a persisted neighbourhood
  snapshot); ~~auto-classify each alert into a named laundering
  typology (FATF / Wolfsberg playbooks) with confidence, evidence
  chips, and an auto-generated SAR narrative~~ (✅ shipped, day-30 —
  6-typology classifier with severity-floor priority promotion, mirrored
  onto every case row, surfaced as a `TypologyBadge` in the queue and a
  full `TypologyPanel` in the case detail + AML console);
  ~~model validation / backtest harness — replay the engine against
  labelled outcomes, report the precision/recall trade-off + ROC AUC +
  per-detector discrimination so rule tuning is evidence-driven~~
  (✅ shipped, day-35 — `backtest.py` + `/validation` console: confusion
  sweep, ROC/PR, Fβ-recommended cut, per-detector single-feature AUC,
  and a what-if loop that validates a weights override against the
  canonical rule set);
  ~~behavioral-drift / anomaly layer — catch accounts whose recent
  behavior no longer matches their own historical baseline (sleeper
  takeovers, mule recruitment, slow operator shifts) using
  distribution-distance statistics, complementary to the rule engine~~
  (✅ shipped, day-40 — `drift.py` + `/drift` console: 10-axis
  fingerprint, 5-band verdict, rolling-KS change-point onset,
  per-counterparty contribution, portfolio ranking);
  ~~adverse-media OSINT — the tier-2 EDD layer that sits above the
  closed-watchlist sanctions screener and answers the open-world
  question: *what is the world saying about this entity?*~~
  (✅ shipped, day-45 — `media.py` + `/media` console: 40-article
  corpus across 11 categories × 3 source tiers, similarity ×
  severity × tier × recency composite, `adverse_media` detector
  wired into the risk engine);
  ~~customer-level composite risk rating — the FATF Recommendation-10
  composite that fuses every TITAN surface (AML, sanctions, adverse
  media, typology, drift, network) into one number per customer
  with a regulator-aligned bucket, FATF-aligned KYC refresh
  cadence, and analyst-override audit trail~~
  (✅ shipped, day-50 — `profile.py` + `/profile` console:
  6-surface deterministic composite, 4-band buckets with refresh
  cadence baked in, append-only history, analyst-override dialog
  with audit-grade justification, portfolio overview).
