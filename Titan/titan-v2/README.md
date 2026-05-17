# TITAN v2

**Trusted Identity & Transaction Authentication Network.**
Document-grade KYC + on-chain attestation + a deterministic, explainable AML
risk engine **with built-in sanctions screening**, a real **case management
workflow**, a **network-intelligence layer** that catches money-laundering
patterns single-account scoring misses, **and** — as of day-25 — a
**network panel that lives inside the case detail itself**, so an analyst
opening any case sees the resolved-entity subgraph, the counterparties
driving the score, and a "what if we clear this?" simulation without ever
leaving the workflow.

> **Day-25 — Network-aware Case Detail.** Day-20 shipped network
> intelligence as a standalone `/network` route, but the case workflow
> (day-15) and the network engine were still two doors away. They are
> now one door. When a case is opened the AML console snapshots the
> 1-hop neighbourhood around the subject account, and the case detail
> auto-runs entity resolution + biased PageRank + leave-one-counterparty
> out against that snapshot the moment the page mounts. The new
> `CaseNetworkPanel` shows:
>
> - **solo vs network risk** — and the lift from peer effects so an
>   account looking *clean by itself* but tainted by neighbours surfaces
>   as visibly suspicious
> - the **1-hop entity subgraph** (deterministic FR layout) centred on
>   the case's resolved entity, with the existing `RiskGraph` visuals
> - **per-counterparty attribution bars** — member-aware: when the
>   subject is an aggregate cluster like `M1+M2 → Trident Exports`,
>   leave-one-out runs across all members at once with per-member
>   baseline scores listed
> - **"if cleared" deltas** — ablate this case's entity, rerun the
>   whole pipeline, report the network-avg change, alerted-count flip,
>   and the **peers that depend most** on the subject (sorted by
>   biggest network drop)
>
> Two endpoints make it work — `GET /aml/cases/{id}/network` runs against
> the persisted snapshot, `POST /aml/cases/{id}/network/clearing`
> accepts caller-supplied transactions for the override path.
>
> All deterministic — same input → same clusters, same propagated scores,
> same layout coordinates. No ML, no embeddings, no animation jitter.

---

## What it does

| Stage | Endpoint | Notes |
|---|---|---|
| KYC ingest | `POST /kyc/verify` | PDF → SHA-256 → IPFS pin (Kubo) → on-chain attest |
| Attestation lookup | `GET  /attest/{docHash}` | Reads `AttestationRegistry.attestations[hash]` |
| Recent attestations | `GET  /attestations/recent` | Replays `Attested` events for the explorer feed |
| AML score | `POST /aml/score` | 8 detectors → 0..100 risk per account; accepts `weights` override |
| AML rules | `GET  /aml/rules` | Auditor-facing dump of weights / thresholds / watchlist meta |
| SAR draft | `POST /aml/sar` | Markdown narrative + structured payload |
| Sanctions screen | `POST /aml/sanctions/screen` | Fuzzy-match a batch of names against the watchlist |
| Sanctions list | `GET  /aml/sanctions/list` | Paged dump of bundled watchlist entries |
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
| `structuring`     | 26 | ≥3 transfers in `[40k, 50k)` within 24h (CTR-evasion proxy) |
| `velocity_spike`  | 16 | recent 1h volume ≥ 5× the trailing 30d baseline rate |
| `round_trip`      | 20 | a closed cycle of length ≤4 with every leg ≥ ₹50 000 |
| `sanctions_hit`   | 22 | subject or counterparty name matches the watchlist ≥ 65% similarity |
| `fan_in`          |  8 | distinct senders ≥ 8 |
| `fan_out`         |  8 | distinct recipients ≥ 8 |
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

## Frontend

| Route | Purpose |
|---|---|
| `/` | Hero + 4-step pipeline + six feature cards + flow diagram |
| `/aml` | Drag-drop CSV → ranked accounts, factor bars, transaction graph, sanctions hits, **what-if weight sliders**, SAR draft, **+ case promotion (per-row chip and bulk header button)**, + `Network →` deep-link |
| `/network` | **(new)** Resolved entities, risk-coloured force graph, sortable sidebar, counterfactual ablation panel, per-account attribution view |
| `/cases` | Kanban-style queue: 6-tile stats banner, priority swim lanes (critical/high/medium), low-priority collapsed list, search + assignee + SLA filters, live nav badge |
| `/cases/{id}` | Big alert ring, priority/SLA pills, frozen evidence snapshot (factor bars + tx graph), **network panel** auto-running entity resolution + propagation + member-aware attribution + "if cleared" deltas on the case's snapshot, sanctions hits panel, status workflow buttons, assignment widget, note composer, full **timeline** rail, attached SAR with collapsible markdown view |
| `/watchlist` | Batch screening (paste names, set jurisdiction prior + similarity floor), per-query result cards with a `SimilarityRing` and component-level breakdown, plus a searchable browse view of the bundled watchlist |
| `/kyc` | PDF dropzone, animated 3-stage pipeline, on-chain receipt with deep-link to explorer |
| `/attestations` | Search by `docHash`, live `Attested` event feed, click-through to detail |

Built with Next.js 14 + Tailwind + a small set of inline SVG components
(`ScoreRing`, `SimilarityRing`, `FactorBars`, `TxGraph`, `PriorityDot`,
`AgePill`, `Timeline`, `CasesNavPill`, `RiskGraph`, `EntityCard`,
`DeltaBar`, `CaseNetworkPanel`). No charting libs.

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
    risk.py             8 detectors + weight-override support
    sanctions.py        token-set + n-gram + containment matcher
    sar.py              markdown narrative + structured payload
    cases.py            SQLite-backed case store + workflow engine + SLA
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
  snapshot).
