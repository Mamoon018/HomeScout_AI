# R2 and R3 over HTTP: Traceflow (Start, Checkpoint, Retry, Status)

## Context

**Why this document exists.** [R2_R3_Independent_Services_Problem_Context.md](R2_R3_Independent_Services_Problem_Context.md)
defines the components that turn R2 (Amenity Search, R2-C1–C8) and R3 (Specific Metric
Resolution, R3-C1–C9) into independent services. Each one has its own state, table, endpoints,
step checkpoints and retry. The process flow describes each component on its own. This traceflow
follows **one customer through each service's three endpoints**, box by box, so you can see where
each component acts, what data moves, where a step is saved, and where the flow can drift or break.

**What it covers.**
- **Covered:** the problem statement and the finalized approaches only. That means auth, endpoints, coordinator, store, state, statuses, checkpoints, the single-execution guard, retry and refresh recovery.
- **Black boxes:** R2's and R3's business logic (discovery, enrichment, attachment, STEP 1–5) is shown as single steps, because it is reused as-is. R3's inside view is in [R3_M1_Traceflow.md](R3_M1_Traceflow.md).

**How to read it.** R2 is Part A and R3 is Part B. Every endpoint is traced as a chain of boxes,
and every box has:

- `in:` what the box receives
- `do:` what the box does
- `exit:` every way the box can end, and where each exit goes

> This is an understanding artifact. It is derived from the process flow and does not change it.
> Points marked ⚠ are not settled by the process flow; they are collected in each part's
> breaking-point register (A7, B7).

### Legend

```
Stage tags
  [UA]    user action on the page                   [BIZ]   coordinator / service work
  [AUTH]  login check (get_authenticated_user)      [DATA]  database read or write (store)
  [API]   FastAPI route, request model              [RESP]  HTTP response sent to the page
  [BG]    background task (R3 only)                 [UA→]   what the user can do next

Box shape
  ┌─ [TAG] ID · name ──────────     one step
  │ in:   ...                       what it receives
  │ do:   ...                       what it does
  │ exit: ✔ ... ──▶ next box        normal exit
  │       ✖ ... ──▶ response        failure exit
  └────────────────────────────     end of step

Markers
  PAID  the step makes paid Google Places / Routes calls (can fail, costs money)
  LLM   the step makes real LLM calls (can fail, slow, costs tokens)
  WEB   the step makes MCP web-search / scrape calls (can fail, slow, costs money)
  SAVE  a checkpoint: the step's result is written to the run row
  FENCE the write only matches the row at this execution's `attempts` value
  ✅    the process flow decides this point (component given)
  ⚠ An / ⚠ Bn   not settled by the process flow; see A7 / B7
```

### Shared gate (both services, every endpoint)

Every R2 and R3 endpoint passes through the same two boxes before any work, exactly as R1's do.

```
┌─ [AUTH] G1 · Verify login cookie ─────────────────────────────────── existing ──
│ in:   request cookie (access token)
│ do:   get_authenticated_user → AccessTokenVerifier.verify(token)
│ exit: ✔ AuthenticatedUser{user_id = token subject} ──▶ G2
│       ✖ missing / invalid cookie ──▶ 401 {"error":"Not authenticated"}
│       ✖ expired token            ──▶ 401 {"error":..., "code":"token_expired"}
│ ✅ R2-C7 / R3-C8 (router-level Depends, same as R1)
└──────────────────────────────────────────────────────────────────────────────────

┌─ [API] G2 · Route + request model + coordinator ─────────────── R2-C7 / R3-C8 ──
│ in:   path run_id (retry, status), JSON body (start), verified user_id
│ do:   FastAPI parses the body into the request model
│       coordinator injected from app.state (built once in lifespan)
│ exit: ✔ typed request + user_id ──▶ endpoint's first [BIZ]/[DATA] box
│       ✖ body shape wrong / field rule broken ──▶ 422 (FastAPI validation)
│       ✖ app started without service-role key ──▶ 503 (coordinator is None)
│ RULE  user_id comes from G1 only, never from the body or the path   ✅ as R1 C3
└──────────────────────────────────────────────────────────────────────────────────
```

### The persistence rule, as it shows in the boxes

A `SAVE` box appears only after a step that is **costly or can't be reproduced** *and*
is followed by more external work before the next write. A step followed only by in-memory
work is covered by the **finish write**. A step whose output was degraded by an outage is
**not** saved. ✅ "The Persistence Rule"

---
---

# Part A — R2 · Amenity Search (runs inside the request)

## A1 — The whole customer journey on one page

```
           (customer is logged in; an R1 run is `finished`; page knows r1_run_id + origin)
                                             │
                                             ▼
   ┌─────────────── SCREEN R1: R1 result (category_metric_plans) ───────────────┐
   │  customer (or the page) starts the amenity search for this R1 run         │
   └───────────────────────────────────────┬────────────────────────────────────┘
                                           │  E1  POST /api/amenity-search/runs
                                           │      { r1_run_id, origin, radius_km? }
                                           ▼
                            ┌─ SCREEN W: waiting (R2 work in request, seconds) ─┐
                            └──┬──────────────┬───────────────┬────────────┬────┘
              422 bad origin / │  404 / 409   │ 201 finished  │ 502/503/500 failed
              radius (no run)  │  R1 run not  │               │
                    ▼          │  found / not │               ▼
              fix input        │  finished    │      retryable:true ──▶ SCREEN F: "Retry"
                               ▼              ▼      retryable:false ─▶ SCREEN S: "Start again"
                         SCREEN R1     SCREEN R2: predefined_records          │
                                       (run finished; R3 may read it          │
                                        by run_id)                            │
                                              ▲                               │
                                              │   E2 POST .../runs/{run_id}/retry (no body)
                                              │                               ▼
                                              │                ┌─ SCREEN W: waiting ─┐
                                              │  200 finished  └──┬─────────────┬────┘
                                              └───────────────────┘             │ 409 still
                                                                                │ running / lost
                                                       502/503 failed,          │ claim ──▶ E3
                                                       retryable:false ──▶ SCREEN S

   At any time:  page refresh ──▶ E3 GET /api/amenity-search/runs/{run_id}  (sessionStorage)
                 ──▶ re-renders SCREEN W (running), R2, F or S from the saved row. Nothing changes.
```

**Run status as the customer sees it** (`r2_runs.status`, R2-C4): three values, `running`,
`finished`, `failed`. For `failed`, the page reads `retryable` only. `completed_step` tells the
page how far the run got. ✅ R2-C5, R2-C7

---

## A2 — E1 · Start an R2 run

**Purpose.** Turn a finished R1 run plus a search origin into one `PredefinedMetricsRecord` per
place per category, saving discovery as soon as it completes.

**Trigger.** On SCREEN R1 the customer (or the page automatically) starts the amenity search.

**Endpoint.** `POST /api/amenity-search/runs` · body `{ "r1_run_id": "<uuid>", "origin": {"latitude": .., "longitude": ..}, "radius_km": 2.0 }`

```
┌─ [UA] A-E1.0 · Start amenity search ────────────────────────────────────────────
│ in:   r1_run_id (from R1's reply / sessionStorage), origin, optional radius_km
│ do:   page shows SCREEN W, sends POST with credentials (cookie)
│ exit: ✔ request sent ──▶ G1 ──▶ G2
│ ⚠ A1 where the page gets `origin` from is outside this feature
│ ⚠ A2 no R2 run_id exists until the reply; a refresh now leaves the page nothing to recover
└──────────────────────────────────────────────────────────────────────────────────
        │ r1_run_id, origin, radius_km, user_id
        ▼
┌─ [API] A-E1.1 · Input check (no I/O) ─────────────────────────────────── R2-C7 ──
│ in:   request body
│ do:   origin.latitude / longitude finite · radius_km > 0 (default DEFAULT_RADIUS_KM = 2.0)
│ exit: ✔ ──▶ A-E1.2
│       ✖ ──▶ 422. NO run_id, NO row.
│ ✅ R2 flow step 2 (same rules R2's build_discovery_request checks, run earlier)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [DATA] A-E1.2 · Read R1's finished output ──────────────────── R1RunStore (as-is) ──
│ in:   r1_run_id, user_id
│ do:   R1RunStore.get_finished_output(r1_run_id, user_id)
│       None → R1RunStore.load_run to tell the two cases apart
│ exit: ✔ category_metric_plans ──▶ A-E1.3
│       ✖ no R1 row for this user        ──▶ 404
│       ✖ R1 row exists, not `finished`  ──▶ 409 (status of the R1 run in the body)
│       ✖ database error                 ──▶ 503 "Run storage is unavailable"
│ ✅ R2-C6 "the R1 run must be the same user's and finished"
└──────────────────────────────────────────────────────────────────────────────────
        │ category_metric_plans
        ▼
┌─ [DATA] A-E1.3 · Create the run ──────────────────────────────── R2-C4 + R2-C3 ──
│ in:   new run_id (created ONCE here), user_id, r1_run_id,
│       AmenitySearchState(origin, radius_km, category_metric_plans)     ✅ R2-C1
│ do:   INSERT r2_runs { run_id, user_id, r1_run_id, status:"running", attempts:0,
│                        completed_step:null, state: {version, state}, retryable:false }
│       run_id_var = run_id (every log line carries it)
│ exit: ✔ row exists ──▶ A-E1.4
│       ✖ database error ──▶ 503 (no row, nothing to retry)
│ ✅ R2-C5: a working run is `running`, not R1's "failed, not retryable" placeholder
└──────────────────────────────────────────────────────────────────────────────────
        │ run_id, state, attempts = 0
        ▼
┌─ [BIZ] A-E1.4 · Step `discovery` ─────────────────── AmenitySearch.run_place_discovery ──
│ in:   state (origin, radius_km, category_metric_plans)
│ do:   per category, concurrently:  build request → searchNearby → canonical place set   PAID
│       → state.discovered_places[category_id] = {place_id: CanonicalPlace}
│ exit: ✔ ──▶ A-E1.5
│       ✖ PlaceDiscoveryCallError     (provider)  ──▶ A-E1.9  retryable
│       ✖ PlaceDiscoveryRequestError  (bad plan)  ──▶ A-E1.9  not retryable
│ ✅ R2-C2 (method reused as-is; called by the coordinator's step list)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [DATA] A-E1.5 · Checkpoint after discovery ────────────────────── SAVE · FENCE ──
│ in:   state with discovered_places
│ do:   UPDATE r2_runs SET state = R2-C3 JSON, completed_step = "discovery"
│       WHERE run_id AND user_id AND status = "running" AND attempts = <mine>
│ exit: ✔ 1 row ──▶ A-E1.6
│       ✖ 0 rows (a newer execution owns the row) ──▶ log r2_run.superseded, stop, 409
│       ✖ database error ──▶ A-E1.9 (save failed quietly; the row may stay `running`
│                            ──▶ reclaimable after stale_after)
│ ✅ R2-C2 table: discovery is costly + non-reproducible + external work follows
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] A-E1.6 · Step `enrichment` ─────────── AmenitySearch.run_accessibility_enrichment ──
│ in:   state.discovered_places
│ do:   unique place index (drop places with no location)
│       concurrently: routing re-search per category × mode (walk/drive/cycle)   PAID
│                     transit matrix per ≤100 places                              PAID
│       → state.enrichment[place_id] = EnrichmentBundle
│       (no place with a location → returns early; counts as completed)
│ exit: ✔ ──▶ A-E1.7   (NO save here)
│       ✖ RoutingRetrievalError / TransitRetrievalError (provider) ──▶ A-E1.9 retryable
│ ✅ R2-C2 "no separate save: the next step has no I/O"
│ ⚠ A3 on a resume, the routing re-search runs minutes/hours after the saved discovery
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] A-E1.7 · Step `attachment` (no I/O) ──────────── AmenitySearch.run_result_attachment ──
│ in:   state.discovered_places, state.enrichment, state.category_metric_plans
│ do:   join profile + accessibility + plan → state.predefined_records[cat][place]
│       (place never enriched → all-null routing, WARN attachment.accessibility_degraded)
│ exit: ✔ ──▶ A-E1.8
│       ✖ ResultAssemblyError (a discovered category has no plan) ──▶ A-E1.9 not retryable
│ ✅ R2-C2 (pure, covered by the finish write)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ├────────────────────────────────────────────┐
        ▼                                            ▼
┌─ [DATA] A-E1.8 · Save as finished ── FENCE ┐  ┌─ [DATA] A-E1.9 · Save as failed ── FENCE ──────┐
│ status = finished                          │  │ status = failed                                │
│ state  = final state (R2-C3 JSON)          │  │ failure_stage = error.stage ("unexpected" for  │
│ output = { category_metric_plans,          │  │                 a non-R2 exception)            │
│            discovered_places,              │  │ failure_message                                │
│            predefined_records }            │  │ retryable = rule (R2-C6 table) AND             │
│ retryable = false                          │  │             attempts < MAX_RETRY_ATTEMPTS (1)  │
│ completed_step unchanged                   │  │ state, completed_step UNTOUCHED                │
│ ✔ ──▶ A-E1.10a                             │  │ ✔ / store down (logged only) ──▶ A-E1.10b      │
│ ✖ 0 rows ──▶ superseded, 409               │  │ ✅ R2-C4 "save as failed never touches state"  │
│ ✖ db error ──▶ 503; row stays running      │  │                                                │
│ ✅ R2-C4 output column for R3              │  │                                                │
└────────────────────────────────────────────┘  └────────────────────────────────────────────────┘
        │                                            │
        ▼                                            ▼
┌─ [RESP] A-E1.10a ──────────────────────────┐  ┌─ [RESP] A-E1.10b ──────────────────────────────┐
│ 201 { run_id, status:"finished",           │  │ 503 provider unavailable · 502 other R2 error  │
│       completed_step:"discovery",          │  │ 500 unexpected                                 │
│       result: predefined_records }         │  │ { run_id, status:"failed", retryable }         │
└────────────────────────────────────────────┘  └────────────────────────────────────────────────┘
        │                                            │
        ▼                                            ▼
┌─ [UA→] A-E1.11 · What the page does with the reply ─────────────────────────────
│ always: save run_id in sessionStorage
│ finished              ──▶ SCREEN R2 (render predefined_records)
│ failed, retryable:true  ──▶ SCREEN F "Retry" (──▶ E2)
│ failed, retryable:false ──▶ SCREEN S "Start again" (new E1)
└──────────────────────────────────────────────────────────────────────────────────
```

**Cancellation inside E1** (shutdown, or the client disconnects if that cancels the handler, ⚠ A4):
whichever box is running raises `CancelledError`. The coordinator saves the run as failed with
`retryable = attempts < MAX` (best effort), then re-raises. ✅ R2-C6 table

**A-E1 exits at a glance**

| Exit | HTTP | Row after it | Screen next |
|---|---|---|---|
| Not logged in / token expired | 401 | none | login, or refresh then resend |
| Bad origin / radius / body | 422 | none | fix input |
| R1 run missing or another user's | 404 | none | SCREEN R1 / start again |
| R1 run not finished | 409 | none | finish R1 first |
| Database down before the row | 503 | none | try again later |
| Finished | 201 | `finished`, `completed_step=discovery`, state + output | SCREEN R2 |
| Places/Routes failure in discovery | 502/503 | `failed`, `retryable:true`, `completed_step=null` | SCREEN F |
| Places/Routes failure in enrichment | 502/503 | `failed`, `retryable:true`, `completed_step=discovery` | SCREEN F |
| Bad plan (request / assembly error) | 502 | `failed`, `retryable:false` | SCREEN S |
| Unexpected error | 500 | `failed`, `retryable:false`, stage `unexpected` | SCREEN S |
| Lost fence | 409 | owned by the newer execution | call E3 |

---

## A3 — E2 · Retry an R2 run

**Purpose.** Finish a failed or crashed run from its last saved step, with at most one
execution live at a time, without repeating finished steps.

**Trigger.** On SCREEN F (`failed`, `retryable:true`) the customer clicks Retry, or the page
offers Retry after a run stayed `running` past `stale_after` (⚠ A5).

**Endpoint.** `POST /api/amenity-search/runs/{run_id}/retry` · no body

```
┌─ [UA] A-E2.0 · Click Retry ─────────────────────────────────────────────────────
│ in:   run_id (sessionStorage)
│ do:   POST with cookie, no body; SCREEN W
│ exit: ✔ ──▶ G1 ──▶ G2
│ (double-click / two tabs → two requests: safe, A-E2.3 lets only one through)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] A-E2.1 · Load the run ────────────────────────────────── R2-C4 + R2-C3 ──
│ do:   SELECT r2_runs WHERE run_id AND user_id; decode state + version check
│ exit: ✔ status, retryable, attempts, completed_step, updated_at, state ──▶ A-E2.2
│       ✖ no row / other user's ──▶ 404
│       ✖ version mismatch      ──▶ save failed, retryable:false ──▶ 409 (as R1)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] A-E2.2 · Retry pre-check (fast reject, not the guard) ──────────── R2-C6 ──
│ in:   status, retryable, attempts, updated_at
│ do:   finished                                   → reject
│       failed AND (NOT retryable OR attempts ≥ 1) → reject
│       running AND updated_at ≥ now − stale_after → reject (still alive)
│ exit: ✔ ──▶ A-E2.3
│       ✖ ──▶ 409 { run_id, status, retryable }
│ ✅ R2-C5 (MAX_RETRY_ATTEMPTS = 1; stale_after = 10 min)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] A-E2.3 · Claim the run (THE guard) ──────────────────────── R2-C5 ──
│ in:   n = attempts read in A-E2.1, stale cutoff
│ do:   ONE conditional UPDATE:
│         SET status = "running", attempts = n + 1, retryable = false
│         WHERE run_id AND user_id AND attempts = n
│           AND ( (status = "failed" AND retryable = true)
│              OR (status = "running" AND updated_at < cutoff) )
│ exit: ✔ 1 row  ──▶ A-E2.4   (this execution's fence value is now n + 1)
│       ✖ 0 rows ──▶ 409 "Another retry of this run already started"; runs nothing
│ ✅ R2-C5 Approach 2 · same shape as R1's mark_retry_started
│ ⚠ A6 the OR of two conditions has to be expressed through supabase-py / PostgREST
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] A-E2.4 · Resume the step plan ─────────────────────────────── R2-C2 ──
│ in:   state from A-E2.1, completed_step
│ do:   completed_step = null        → A-E1.4 discovery → A-E1.5 SAVE → A-E1.6 → A-E1.7
│       completed_step = "discovery" → A-E1.6 enrichment → A-E1.7          (discovery NOT rerun)
│       every write uses FENCE attempts = n + 1
│ exit: ✔ ──▶ A-E1.8 save finished ──▶ 200 { run_id, finished, completed_step, result }
│       ✖ R2 error ──▶ A-E1.9 save failed, retryable:false (limit used) ──▶ 502/503/500
│       ✖ lost fence ──▶ 409
│ ✅ R2-C2 resume rule; R2-C8 "discovery is called once in total"
└──────────────────────────────────────────────────────────────────────────────────
```

**A-E2 exits at a glance**

| Exit | HTTP | Row after it | Screen next |
|---|---|---|---|
| Run missing or another user's | 404 | unchanged | SCREEN S |
| Version mismatch | 409 | `failed`, `retryable:false` | SCREEN S |
| Finished / not retryable / limit used | 409 | unchanged | SCREEN R2 or S |
| Still running, not stale | 409 `status:running` | unchanged | keep polling E3 |
| Lost the claim to another request | 409 | owned by the winner | call E3 |
| Finished | 200 | `finished`, state + output | SCREEN R2 |
| Fails again | 502/503/500 | `failed`, `retryable:false` | SCREEN S |

---

## A4 — E3 · Status (refresh recovery)

**Purpose.** After a refresh, a lost reply, or a `409`, show the screen that matches the saved run
without doing any work.

**Endpoint.** `GET /api/amenity-search/runs/{run_id}`

```
┌─ [UA] A-E3.0 · Page load / resync ──────────────────────────────────────────────
│ do:   read run_id from sessionStorage
│ exit: ✔ found ──▶ GET ──▶ G1 ──▶ G2      ✖ not found ──▶ SCREEN R1
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] A-E3.1 · Load the run (read-only) ─────────────────────── R2-C4 + R2-C3 ──
│ do:   SELECT by run_id + user_id; decode output (state only if needed)
│       NO Places/Routes calls, NO writes
│ exit: ✔ ──▶ A-E3.2
│       ✖ 404 ──▶ clear sessionStorage ──▶ SCREEN R1
│       ✖ version mismatch ──▶ 200 { status:"failed", retryable:false } without writing (as R1)
│       ✖ database error   ──▶ 503
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [RESP] A-E3.2 · Reply by status ────────────────────────────────────── R2-C7 ──
│ running  ──▶ 200 { run_id, status, completed_step }            ──▶ SCREEN W
│ finished ──▶ 200 { run_id, status, completed_step, result }    ──▶ SCREEN R2
│ failed   ──▶ 200 { run_id, status, completed_step, retryable } ──▶ SCREEN F or S
│ ⚠ A5 a `running` row that is already stale (crashed) still reads as `running`
└──────────────────────────────────────────────────────────────────────────────────
```

---

## A5 — The R2 run row: lifecycle and data actions

### A5.1 Status lifecycle

```
   (no row) ── 422 / 404 / 409 before the row ──▶ (still no row)
      │
      │ A-E1.3 INSERT                    attempts = 0, completed_step = null
      ▼
   running ──A-E1.5 SAVE──▶ running (completed_step = discovery) ──A-E1.8──▶ finished
      │                          │
      │ A-E1.9                   │ A-E1.9
      ▼                          ▼
   failed (retryable per rule)   failed (retryable per rule, checkpoint kept)
      │                          │
      └──────────┬───────────────┘        running + stale (crash: no write for stale_after)
                 │                                       │
                 └──────── A-E2.3 claim: attempts 0 → 1 ─┘
                                       ▼
                                    running ──resume──▶ finished
                                       │
                                       └──▶ failed (retryable:false, limit used)

   finished is terminal. failed + retryable:false is terminal ("Start again" = new E1).
   R1 run deleted ──▶ cascade deletes the R2 row; a live execution's next write matches nothing.
```

### A5.2 Data actions per endpoint, in order

| # | Endpoint | Store operation (R2-C4) | Columns written | Filter |
|---|---|---|---|---|
| 1 | E1 | (R1) Get the finished output | — (read `r1_runs.output`) | `r1_run_id`, `user_id`, `finished` |
| 2 | E1 | Create a run | all initial columns, `status=running` | — (insert) |
| 3 | E1 | Save a checkpoint | `state`, `completed_step=discovery` | `running`, `attempts=n` |
| 4 | E1 | Save as finished | `status`, `state`, `output`, `retryable=false` | `attempts=n` |
| 4' | E1 | Save as failed | `status`, `failure_*`, `retryable` | `attempts=n` |
| 5 | E2 | Load a run | — (read) | `run_id`, `user_id` |
| 6 | E2 | Claim for retry | `status=running`, `attempts=n+1`, `retryable=false` | `attempts=n` + (failed∧retryable ∨ running∧stale) |
| 7 | E2 | Checkpoint / finished / failed | as 3 / 4 / 4' | `attempts=n+1` |
| 8 | E3 | Load a run | — (read) | `run_id`, `user_id` |
| 9 | R3 | Get the finished output | — (read `output`) | `finished` |

Every read and write filters on `run_id` **and** `user_id`. Every write is one single-row
statement. ✅ R2-C4

### A5.3 Paid calls per path (cost and wait time on SCREEN W)

With `C` categories and `P` distinct places (≤ 10 per category):

| Path | Places / Routes calls inside the request |
|---|---|
| E1, full run | discovery `C` · routing `3·C` · transit `⌈P/100⌉` |
| E2 after a failure in discovery (`completed_step=null`) | same as the full run |
| E2 after a failure in enrichment (`completed_step=discovery`) | routing `3·C` · transit `⌈P/100⌉` (discovery saved) |
| E3 | none |

---

## A6 — How R2 hands over to R3

```
r2_runs.output (status = finished)
   { category_metric_plans, discovered_places, predefined_records }       ✅ R2-C1 handoff
        │  read by R3 through R2RunStore.get_finished_output(r2_run_id, user_id)
        ▼
SpecificMetricResolutionState(category_metric_plans, discovered_places, predefined_records)
   (enrichment is NOT handed over: R3 never reads it)
```

---

## A7 — R2 breaking points and drift register

Each point names the box where it shows up, what goes wrong, and whether the process flow
covers it.

### A7.1 Product level (what the customer experiences)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| A1 | A-E1.0 | The request needs `origin`, but nothing in R1 or this feature says where the page gets it (apartment address, map pin, …). | ⚠ open (outside this feature) |
| A2 | A-E1.0 | The run ID reaches the page only with the reply. A refresh during the start request leaves the page with nothing to recover, as in R1's B2. Short for R2 (seconds). | ⚠ open, low impact |
| A5 | A-E3.2 | After a hard crash, the row stays `running`. For up to `stale_after` (10 min) the page shows "waiting", and retry returns `409 running`. The page can't tell a live run from a dead one, because the status reply carries no "stale" signal. | ⚠ open: add `retryable:true` to a stale `running` reply, or let the page offer Retry after a timeout |
| A8 | A-E1.10b | A non-retryable failure (bad plan) can only be fixed upstream in R1. The customer sees "Start again" for R2, but starting R2 again with the same R1 run fails the same way. | ⚠ open: the page should send the customer back to R1 |
| A9 | A5.1 | Two R2 runs for the same R1 run are allowed. Each costs a full set of Places calls. | ✅ decided (R2-C6), cost note only |

### A7.2 Technical level (what the code must handle)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| A3 | A-E1.6 / A-E2.4 | Enrichment re-searches Places per category and mode, and joins by `place_id`. On a resume, it runs long after the saved discovery, so the re-search can return different places. Places missing from it get all-null routing (an existing WARN). The logic is unchanged, but the gap widens. | ✅ accepted (logic unchanged); shows as `attachment.accessibility_degraded` |
| A4 | A-E1.4–A-E1.7 | Whether a client disconnect cancels the handler (`log_requests` is an `http` middleware) isn't known. If it does, the run is saved as failed and retryable. If it doesn't, the run finishes and E3 shows it. | ⚠ confirm in R2-C8 |
| A6 | A-E2.3 | The claim needs `attempts = n AND ((failed ∧ retryable) ∨ (running ∧ updated_at < cutoff))` in one statement. supabase-py supports `.or_()` with nested `and(...)`, but the timestamp format and escaping need care. The fallback is two conditional updates tried in order, each still atomic. | ⚠ implementation detail; R2-C8 "concurrent retries" proves it |
| A10 | A-E1.5 / A-E1.8 | The database is down after paid work succeeded. A checkpoint failure loses discovery. A finish failure loses enrichment, but discovery is saved. Either way the row stays `running`, becomes stale after 10 min and can be reclaimed. | ✅ covered by R2-C5 (cost of the lost step only) |
| A11 | A-E1.9 | The cancellation row in the R2-C6 table says "Yes" (retryable) without repeating the retry limit. This traceflow applies `attempts < MAX`, so a cancelled retry becomes not retryable. | ⚠ drift: confirm in R2-C6 |
| A12 | A-E2.1 | The pre-check reads `updated_at` written by the database trigger (`clock_timestamp()`), and the cutoff is computed from the backend clock. Clock skew shifts staleness by the skew. | ✅ accepted (R2-C5: value ≫ skew) |

### A7.3 Architectural level (how the pieces fit)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| A13 | A-E1.4–A-E1.8 | R2 runs inside the request. That is right for seconds, but more categories or slower Places responses lengthen it, and nothing alerts when it nears proxy timeouts. | ✅ chosen (R2-C6); revisit if run time grows |
| A14 | R2-C4 | The service-role key bypasses RLS. Isolation depends on every query adding `user_id`. | ✅ accepted, as R1; tested in R2-C8 |
| A15 | R2-C3 | The saved state is tied to `R2_STATE_SCHEMA_VERSION`. A deploy that changes `AmenitySearchState` fails in-flight runs as not retryable. | ✅ accepted, as R1 |
| A16 | R2-C4 | Google Places content is kept in `state` / `output` with no expiry. | ✅ decided: kept for now; the policy comes in a later phase |

### A7.4 Where to look first

1. **A5:** a crashed run looks alive for up to 10 minutes.
2. **A6:** the claim statement has to be truly one atomic update.
3. **A11:** the retry limit on cancellation.
4. **A4:** disconnect behavior in the middleware.

---
---

# Part B — R3 · Specific Metric Resolution (runs in a background task)

## B1 — The whole customer journey on one page

```
             (customer is logged in; an R2 run is `finished`; page knows r2_run_id)
                                             │
                                             ▼
   ┌─────────────── SCREEN R2: amenity records (predefined_records) ────────────┐
   │  customer (or the page) starts metric resolution for this R2 run          │
   └───────────────────────────────────────┬────────────────────────────────────┘
                                           │  E1  POST /api/specific-metric-resolution/runs
                                           │      { r2_run_id }
                                           ▼
                 404 / 409 R2 run ◀──┬─────┴───── 202 { run_id, status:"running" } (immediately)
                 not found / not     │                     │
                 finished            │                     ▼
                       ▼             │      ┌─ SCREEN P: progress (polls E3 every few s) ──────┐
                  SCREEN R2          │      │ completed_step: null → "discovery_batch"         │
                                     │      │ ("websites found, resolving metrics")            │
                                     │      └──┬────────────────────┬──────────────────────────┘
                                     │         │ status finished    │ status failed
                                     │         ▼                    ▼
                                     │   SCREEN R3: result    retryable:true ──▶ SCREEN F "Retry"
                                     │   (resolution_results) retryable:false ─▶ SCREEN S "Start again"
                                     │         ▲                    │
                                     │         │                    │ E2 POST .../runs/{run_id}/retry
                                     │         │                    ▼
                                     │         │     202 { status:"running" } ──▶ SCREEN P (polls)
                                     │         └────────────── finished ◀──┘
                                     │
   At any time:  page refresh ──▶ E3 GET /api/specific-metric-resolution/runs/{run_id}
                 ──▶ SCREEN P (running), R3, F or S from the saved row. Nothing changes.
```

**What differs from R1 and R2:** start and retry return **`202` before any work**. All work
happens in a background task, and the page learns the outcome only by polling E3. ✅ R3-C7, R3-C8

---

## B2 — E1 · Start an R3 run

**Purpose.** Create the run from a finished R2 run, answer at once, and resolve the specific
metrics in the background, saving STEP 3 as soon as it completes cleanly.

**Endpoint.** `POST /api/specific-metric-resolution/runs` · body `{ "r2_run_id": "<uuid>" }`

### B2.1 The request part (returns in milliseconds)

```
┌─ [UA] B-E1.0 · Start metric resolution ─────────────────────────────────────────
│ in:   r2_run_id (from R2's reply / sessionStorage)
│ do:   POST with cookie
│ exit: ✔ ──▶ G1 ──▶ G2
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] B-E1.1 · Read R2's finished output ─────────────────────────── R2-C4 ──
│ in:   r2_run_id, user_id
│ do:   R2RunStore.get_finished_output(r2_run_id, user_id); None → load to tell apart
│ exit: ✔ { category_metric_plans, discovered_places, predefined_records } ──▶ B-E1.2
│       ✖ no R2 row for this user ──▶ 404       ✖ R2 not finished ──▶ 409
│       ✖ database error          ──▶ 503
│ ✅ R3-C7 "checked before the row is created"
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] B-E1.2 · Create the run ─────────────────────────────────── R3-C5 + R3-C4 ──
│ in:   new run_id, user_id, r2_run_id,
│       SpecificMetricResolutionState(category_metric_plans, discovered_places,
│                                     predefined_records)                    ✅ R3-C1
│ do:   INSERT r3_runs { run_id, user_id, r2_run_id, status:"running", attempts:0,
│                        completed_step:null, state:{version, state}, retryable:false }
│       (tuple-keyed dicts are empty here; encoded as lists when filled, R3-C4)
│ exit: ✔ ──▶ B-E1.3      ✖ database error ──▶ 503 (no row)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-E1.3 · Schedule the background task ─────────────────────────── R3-C7 ──
│ do:   task = asyncio.create_task(execute(run_id, user_id, state, attempts=0,
│                                          resume_after=None))
│       app.state.r3_tasks.add(task); task.add_done_callback(r3_tasks.discard)
│ exit: ✔ ──▶ B-E1.4
│ ✅ R3-C7 "keeping tasks alive"
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [RESP] B-E1.4 ─────────────────────────────────────────────────────── R3-C8 ──
│ 202 { run_id, status:"running" }
│ [UA→] save run_id in sessionStorage ──▶ SCREEN P, poll E3
└──────────────────────────────────────────────────────────────────────────────────
```

### B2.2 The background part (minutes)

```
┌─ [BG] B-BG.0 · Task start ──────────────────────────────────────── R3-C7 + R3-C2 ──
│ in:   run_id, user_id, state, fence n (attempts), resume_after
│ do:   run_id_var = run_id
│       r3 = create_specific_metric_resolution(settings, llm_caller=shared)
│            → NEW McpToolGateway for this run only; owns_caller = False
│ exit: ✔ ──▶ B-BG.1
│ ✅ R3-C2 one instance per run (a shared gateway would be closed by another run's finally)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-BG.1 · r3.run_specific_metric_resolution(state, resume_after, on_step_completed) ──
│ ┌─ unchanged method body (inside view: R3_M1_Traceflow.md) ─────────────────────────────┐
│ │ caller check · breaker = new _CircuitBreaker(threshold)        (fresh on every attempt)│
│ │ gateway.open()   Parallel + Firecrawl sessions, capability check                       │
│ │   ✖ McpConnectionError (retryable) · McpToolUnavailableError (not retryable)           │
│ │ STEP 1 plan_index · STEP 2 work items       (always recomputed from saved inputs)      │
│ │ phase-1 catalog (if work items) ✖ MetricResolutionValidationError (not retryable)      │
│ │                                                                                        │
│ │ resume_after == "discovery_batch" ?                                                    │
│ │   YES ──▶ skip STEP 3 (verdicts already in state.website_search_results)               │
│ │   NO  ──▶ STEP 3 DISCOVERY BATCH   gate pre-pass → website discovery fan-out  LLM WEB  │
│ │           ╌╌ barrier: every work item has a verdict ╌╌                                 │
│ │           await on_step_completed("discovery_batch", state, breaker.open) ──▶ B-BG.2   │
│ │                                                                                        │
│ │ STEP 4 AMENITY PIPELINES  phase 1 → triage → phase 2 → resolution turn   LLM WEB       │
│ │           ╌╌ barrier: all pipelines returned ╌╌                                        │
│ │ STEP 5 sweep → state.resolution_results · run-level raise                              │
│ │   ✖ MetricResolutionProviderError(cause: availability | circuit_open | content)        │
│ │ finally: gateway.aclose()                                                              │
│ └────────────────────────────────────────────────────────────────────────────────────────┘
│ exit: ✔ final state ──▶ B-BG.3
│       ✖ any error above, or one raised by the callback ──▶ B-BG.4
│ ✅ R3-C3 Approach 2 (two optional params + one awaited call at the existing barrier)
└──────────────────────────────────────────────────────────────────────────────────
        │ (called from inside STEP 3's barrier)
        ▼
┌─ [DATA] B-BG.2 · Checkpoint after STEP 3 (the callback) ──────────── SAVE · FENCE ──
│ in:   step = "discovery_batch", state, breaker_open
│ do:   breaker_open = true  ──▶ DO NOT SAVE (verdicts are outage-made `none`)     ✅ R3-C3
│       breaker_open = false ──▶ UPDATE r3_runs SET state = R3-C4 JSON,
│                                   completed_step = "discovery_batch"
│                                WHERE run_id AND user_id AND status = running AND attempts = n
│ exit: ✔ saved / skipped ──▶ back into B-BG.1 (STEP 4 starts)
│       ✖ 0 rows    ──▶ raise RunSupersededError  (leaves the method through its finally)
│       ✖ db error  ──▶ raise RunStoreError       (same path)
│ ✅ R3-C3 table: STEP 3 is costly + non-reproducible + STEP 4 follows
└──────────────────────────────────────────────────────────────────────────────────
        │
        ├─────────────────────────────────────────────┐
        ▼                                             ▼
┌─ [DATA] B-BG.3 · Save as finished ── FENCE ┐  ┌─ [DATA] B-BG.4 · Save as failed ── FENCE ──────┐
│ status = finished                          │  │ RunSupersededError → NOTHING saved, log only   │
│ state  = final (tuple keys encoded R3-C4)  │  │ otherwise:                                     │
│ output = resolution_results as a list of   │  │   status = failed, failure_stage, message      │
│   {category_id, place_id, value}           │  │   retryable = rule (R3-C7 table) AND           │
│ retryable = false                          │  │               attempts < MAX (1)               │
│ ✖ 0 rows ──▶ superseded (log)              │  │   state, completed_step UNTOUCHED              │
│ ✖ db error ──▶ log; row stays running      │  │   store down → logged; row stays running       │
│   ──▶ reclaimable after stale_after        │  │   ──▶ reclaimable after stale_after            │
└────────────────────────────────────────────┘  └────────────────────────────────────────────────┘
        │                                             │
        └───────────────────────┬─────────────────────┘
                                ▼
┌─ [BG] B-BG.5 · Task end ─────────────────────────────────────────────── R3-C7 ──
│ finally: await r3.aclose()   (this run's gateway; shared caller NOT closed)
│          task removed from app.state.r3_tasks (done callback)
│ The page sees the outcome only through E3.
└──────────────────────────────────────────────────────────────────────────────────
```

**Shutdown during B-BG.1** (deploy, restart): `lifespan` cancels each task in `r3_tasks` and
awaits it (short timeout). `CancelledError` lands at the current `await`. The method's
`finally` closes the gateway, and the task saves the run as failed with
`retryable = attempts < MAX`, best effort. ✅ R3-C7 "shutdown"

**B-E1 / background outcomes at a glance**

| Outcome | HTTP (E1) | Row after it | E3 shows | Screen |
|---|---|---|---|---|
| R2 run missing / another user's | 404 | none | — | SCREEN R2 |
| R2 run not finished | 409 | none | — | SCREEN R2 |
| Database down before the row | 503 | none | — | try later |
| Accepted | 202 | `running` | `running`, `completed_step` | SCREEN P |
| Finished | (202 earlier) | `finished`, state + output | `result` | SCREEN R3 |
| Gateway can't connect | (202) | `failed`, `retryable:true`, `completed_step=null` | `retryable:true` | SCREEN F |
| Breaker open / provider down in STEP 4 | (202) | `failed`, `retryable:true`, `completed_step=discovery_batch` *if STEP 3 was clean* | `retryable:true` | SCREEN F |
| Breaker opened during STEP 3 | (202) | `failed`, `retryable:true`, `completed_step=null` (STEP 3 not saved) | `retryable:true` | SCREEN F |
| Catalog / tool missing | (202) | `failed`, `retryable:false` | `retryable:false` | SCREEN S |
| Unexpected error | (202) | `failed`, `retryable:false`, stage `unexpected` | `retryable:false` | SCREEN S |
| Shutdown mid-run | (202) | `failed`, `retryable:true` (best effort) | `retryable:true` | SCREEN F |
| Hard crash | (202) | stays `running` | `running` until stale | SCREEN P (⚠ B5) |

---

## B3 — E2 · Retry an R3 run

**Purpose.** Continue a failed or crashed run from its last saved step, in the background, with
one execution live at a time.

**Endpoint.** `POST /api/specific-metric-resolution/runs/{run_id}/retry` · no body

```
┌─ [UA] B-E2.0 · Click Retry ── POST, no body ──▶ G1 ──▶ G2 ─────────────────────────────
        ▼
┌─ [DATA] B-E2.1 · Load the run ────────────────────────────────── R3-C5 + R3-C4 ──
│ do:   SELECT r3_runs by run_id + user_id; decode state (tuple keys rebuilt) + version
│ exit: ✔ ──▶ B-E2.2    ✖ 404    ✖ version mismatch ──▶ save failed, not retryable ──▶ 409
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-E2.2 · Retry pre-check ───────────────────────────────────────── R3-C6 ──
│ same rules as A-E2.2, with stale_after = 30 min
│ exit: ✔ ──▶ B-E2.3      ✖ ──▶ 409 { run_id, status, retryable }
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] B-E2.3 · Claim the run (THE guard) ───────────────────────────── R3-C6 ──
│ same single conditional UPDATE as A-E2.3, on r3_runs
│ exit: ✔ 1 row ──▶ B-E2.4 (fence n + 1)   ✖ 0 rows ──▶ 409 "Another retry … already started"
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-E2.4 · Schedule the resumed task ─────────────────────────────── R3-C7 ──
│ do:   create_task(execute(run_id, user_id, state, attempts = n + 1,
│                           resume_after = completed_step))
│ exit: ✔ ──▶ 202 { run_id, status:"running", completed_step } ──▶ SCREEN P (polls E3)
│ background: B-BG.0 → B-BG.1 with resume_after:
│     null              → STEP 3 runs (and is saved if clean) → STEP 4
│     "discovery_batch" → STEP 3 SKIPPED → STEP 4        (STEP 3 calls made once in total)
│   outcome ──▶ B-BG.3 / B-BG.4 with FENCE n + 1; a failure now is retryable:false
│ ✅ R3-C3 resume rule; R3-C9 "resume parity"
└──────────────────────────────────────────────────────────────────────────────────
```

---

## B4 — E3 · Status (polling and refresh recovery)

**Endpoint.** `GET /api/specific-metric-resolution/runs/{run_id}`

```
┌─ [UA] B-E3.0 · Poll / page load ────────────────────────────────────────────────
│ do:   every few seconds while status is running; also on page load (sessionStorage)
│ exit: ✔ ──▶ G1 ──▶ G2
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] B-E3.1 · Load the run (read-only) ─────────────────────────────── R3-C5 ──
│ do:   SELECT by run_id + user_id. NO LLM, NO web calls, NO writes.
│ exit: ✔ ──▶ B-E3.2   ✖ 404   ✖ version mismatch ──▶ 200 failed, retryable:false (no write)
│       ✖ db error ──▶ 503 (page keeps polling)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [RESP] B-E3.2 · Reply by status ──────────────────────────────────────── R3-C8 ──
│ running  ──▶ 200 { run_id, status, completed_step }        ──▶ SCREEN P
│              completed_step null → "finding websites"
│              completed_step "discovery_batch" → "resolving metrics"
│ finished ──▶ 200 { run_id, status, completed_step, result } ──▶ SCREEN R3
│ failed   ──▶ 200 { run_id, status, completed_step, retryable } ──▶ SCREEN F or S
│ ⚠ B5 a crashed run reads as `running` for up to 30 min
└──────────────────────────────────────────────────────────────────────────────────
```

---

## B5 — The R3 run row: lifecycle and data actions

### B5.1 Status lifecycle

```
   (no row) ── 404 / 409 / 503 before the row ──▶ (still no row)
      │
      │ B-E1.2 INSERT                       attempts = 0, completed_step = null
      ▼
   running ──B-BG.2 SAVE (breaker closed)──▶ running (completed_step = discovery_batch) ──B-BG.3──▶ finished
      │      B-BG.2 SKIP (breaker open)  ──▶ running (completed_step = null)            ──B-BG.4──▶ failed
      │                                                                                    │
      └──B-BG.4──▶ failed (completed_step = null)                                          │
                      │                                                                    │
                      └──────────────┬─────────────────────────────────────────────────────┘
                                     │          running + stale (hard crash, 30 min)
                                     │                         │
                                     └── B-E2.3 claim 0 → 1 ───┘
                                                  ▼
                                        running (resume after completed_step)
                                         ├──▶ finished
                                         └──▶ failed (retryable:false, limit used)

   finished is terminal (including runs with some pipeline_error / resolution_call_failed records).
   R2 run deleted ──▶ cascade deletes the R3 row; a live task's next write matches nothing.
```

### B5.2 Data actions per endpoint, in order

| # | Where | Store operation (R3-C5) | Columns written | Filter |
|---|---|---|---|---|
| 1 | E1 | (R2) Get the finished output | — (read `r2_runs.output`) | `r2_run_id`, `user_id`, `finished` |
| 2 | E1 | Create a run | initial columns, `status=running` | — (insert) |
| 3 | BG | Save a checkpoint (only if breaker closed) | `state`, `completed_step=discovery_batch` | `running`, `attempts=n` |
| 4 | BG | Save as finished | `status`, `state`, `output`, `retryable=false` | `attempts=n` |
| 4' | BG | Save as failed (not on lost fence) | `status`, `failure_*`, `retryable` | `attempts=n` |
| 5 | E2 | Load a run | — (read) | `run_id`, `user_id` |
| 6 | E2 | Claim for retry | `status=running`, `attempts=n+1`, `retryable=false` | as A-E2.3 |
| 7 | BG | Checkpoint / finished / failed | as 3 / 4 / 4' | `attempts=n+1` |
| 8 | E3 | Load a run | — (read, polled) | `run_id`, `user_id` |

### B5.3 Paid work per path (cost and wait time on SCREEN P)

With `N` work items (places in categories with specific metrics) and `D ≤ N` items declined by the
official-URL gate:

| Path | LLM / web work in the background |
|---|---|
| E1, full run | STEP 3: for each of `D`, one search tool turn + one selection turn (LLM ×2, WEB ×1, + retries) · STEP 4: for each of `N`, phase 1 (+retry) · triage · optional phase 2 map/scrape · resolution turn |
| E2, `completed_step = null` (gateway failure, breaker during STEP 3, crash in STEP 3) | same as the full run |
| E2, `completed_step = discovery_batch` | STEP 4 only (STEP 3 saved) |
| E3 | none |

---

## B6 — Where the R3 service itself changes (and where it doesn't)

```
run_specific_metric_resolution(state,                         ◀── annotation: SpecificMetricResolutionState (R3-C1)
                               *, resume_after=None,          ◀── NEW, default = today's behavior (R3-C3)
                                  on_step_completed=None)     ◀── NEW, default = no save (R3-C3)
│ caller check · breaker · open · STEP 1 · STEP 2 · catalog   ── unchanged
├─ if resume_after != "discovery_batch":
│     STEP 3                                                  ── unchanged
│     await on_step_completed("discovery_batch", state, breaker.open)   ◀── NEW (one call)
│ STEP 4 · STEP 5 · finally aclose                            ── unchanged
```

Everything else in R3, including every STEP 3/4 decision, degradation and log line, is untouched.
✅ Scope Boundary

---

## B7 — R3 breaking points and drift register

### B7.1 Product level (what the customer experiences)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| B5 | B-E3.2 | After a hard crash, the row reads `running` for up to 30 min, and retry returns `409 running`. The customer watches a progress screen that will never move. | ⚠ open: report stale `running` as retryable in E3, or let the page offer Retry after a timeout |
| B8 | B5.1 | A run that finishes with some amenities as `pipeline_error` or `resolution_call_failed` is `finished` and can't be retried. Those metrics stay unresolved unless a new R3 run is started (which redoes everything). | ✅ by design (the whole step is the unit; finished is terminal); note for product |
| B9 | B-E1.4 | A start request whose `202` is lost (refresh at that moment) leaves the run going on the server with no `run_id` on the page. | ⚠ open, low impact (the window is milliseconds) |
| B10 | B-E3.0 | Progress is coarse: only `null` → `discovery_batch` → finished. STEP 4 (the longest part) shows no movement. | ✅ accepted (progress isn't in the problem statement) |

### B7.2 Technical level (what the code must handle)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| B11 | R3-C6 | `stale_after = 30 min` must be longer than the longest STEP 4. Nothing measures STEP 4 yet. If STEP 4 runs longer, a live run can be reclaimed and both executions spend money. Fencing keeps the data correct, not the cost. | ⚠ open until R3-C9 records live STEP 4 durations |
| B12 | B-BG.2 | The degraded-STEP-3 rule uses `breaker.open` only. STEP 3 items can also end as `none` from per-item provider failures *below* the breaker threshold, and those are saved. A retry then won't rediscover them. | ⚠ open: accepted as "real result" by today's logic, or extend the rule (for example, don't save when any item degraded on `availability`) |
| B13 | B-BG.0 | One gateway per run (R3-C2) means the Firecrawl token bucket and search semaphores are per run. Two parallel runs can exceed the account's real rate limit and get `429`s (retried by the gateway, then `failed` results). | ✅ accepted for now (R3-C2); cap on active runs is a follow-up |
| B14 | Shutdown | A cancelled task's "save as failed" is itself an `await` on the database during shutdown. If the lifespan timeout is hit first, the row stays `running` (→ B5). | ✅ covered by stale reclaim; ⚠ choose the lifespan timeout |
| B15 | B-BG.1 | A fresh breaker on resume means an outage that lasts across the retry trips the breaker again, and the one retry is used up. | ✅ accepted (retry is manual; the customer retries when ready) |
| B16 | B-BG.1 | STEP 4's internal `run_id = uuid4().hex` differs from the HTTP `run_id`. Logs carry both (the HTTP one via `run_id_var`). | ✅ decided (R3-C3), note for log readers |
| B17 | B-BG.4 | The cancellation row in the R3-C7 table says "Yes" (retryable) without repeating the limit. This traceflow applies `attempts < MAX`. | ⚠ drift: confirm in R3-C7 |
| B18 | B-E2.3 | The same OR-claim statement as A6, on `r3_runs`. | ⚠ as A6 |
| B19 | B-BG.2 | The callback is awaited inside the method's `try` with the gateway open, so a slow database write holds the MCP sessions open a little longer. | ✅ negligible (one row update) |

### B7.3 Architectural level (how the pieces fit)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| B20 | B-E1.3 | Background tasks live in one worker process. With several workers, each worker cancels only its own tasks on shutdown, and a run is owned by whichever worker started it. All state is in `r3_runs`, so this is correct. | ✅ no shared in-memory state needed |
| B21 | B-E1.4 | Start and retry return `202` with no result. R3 is the only service whose action endpoints don't return the outcome, so the page needs one more pattern (polling). | ✅ chosen (R3-C7); consequence noted |
| B22 | R3-C5 | `output` holds `resolution_results` (marked TEMPORARY). When STEP 6 lands, the output becomes `amenity_records` with a version bump, and in-flight runs then fail as not retryable. | ✅ decided (R3-C5) |
| B23 | R3-C4 | The tuple-key encoding exists only in the R3 store. Any other reader of `r3_runs.state` (debug scripts, a future service) must use the store's loader, not plain JSON. | ✅ by design (one place knows the format) |
| B24 | R3-C5 | Places content (`predefined_records`) is also kept in `r3_runs.state`, with no expiry. | ✅ decided: kept for now; the policy comes in a later phase |

### B7.4 Where to look first

1. **B11:** `stale_after` vs real STEP 4 time (double spend if wrong).
2. **B12:** which degraded STEP 3 results get saved.
3. **B5:** a crashed run looks alive for up to 30 minutes.
4. **B17 / A11:** the retry limit on cancellation.
5. **B13:** rate limits with parallel runs.

The rest are product choices, or accepted trade-offs already written into the process flow.
