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
  [BG]    background task (R2, R3)                  [UA→]   what the user can do next

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

# Part A — R2 · Amenity Search (runs in a background task)

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
              422 bad origin / radius (no run) ──▶ fix input
              404 no finished R1 output for user ──▶ SCREEN R1
              503 store down (no run) ──▶ try again
                                           │ 202 { run_id, status:"running" }  (milliseconds)
                                           │ page saves run_id in sessionStorage
                                           ▼
             ┌─ SCREEN W: waiting (R2 runs in a background task, seconds) ─┐
             │  poll E3 GET /api/amenity-search/runs/{run_id} every ~2 s  │◀──┐
             └──┬───────────────────────┬──────────────────────┬───────────┘   │
                │ running               │ finished             │ failed         │
                └──▶ poll again ────────┼──────────────────────┼────────────────┘
                                        ▼                      ▼
                           SCREEN R2: predefined_records   retryable:true ──▶ SCREEN F: "Retry"
                           (run finished; R3 may read it   retryable:false ─▶ SCREEN S: "Start again"
                            by run_id)                               │
                                                                     │ E2 POST .../runs/{run_id}/retry
                                                                     ▼ (no body)
                                                   202 { run_id, status:"running", completed_step }
                                                     ──▶ SCREEN W (polls E3 again)
                                                   409 not retryable / still running / lost claim
                                                     ──▶ E3

   At any time:  page refresh ──▶ E3 (run_id from sessionStorage) ──▶ re-renders SCREEN W
                 (and keeps polling), R2, F or S from the saved row. The run is not affected.
```

**Run status as the customer sees it** (`r2_runs.status`, R2-C4): three values, `running`,
`finished`, `failed`. For `failed`, the page reads `retryable` only. `completed_step` tells the
page how far the run got. ✅ R2-C5, R2-C7

---

## A2 — E1 · Start an R2 run

**Purpose.** Turn a finished R1 run plus a search origin into one `PredefinedMetricsRecord` per
place per category, saving discovery as soon as it completes.

**Shape (R2-C6 Iteration 2).** E1 has two parts. The **request part** (A-E1.0 to A-E1.3b) checks
the input, creates the row, starts a background task and replies `202` in milliseconds. The
**background part** (A-E1.4 to A-E1.10b) runs the steps and saves the outcome to the row. The
page learns the outcome only by polling E3 (A-E1.11).

**Trigger.** On SCREEN R1 the customer (or the page automatically) starts the amenity search.

**Endpoint.** `POST /api/amenity-search/runs` · body `{ "r1_run_id": "<uuid>", "origin": {"latitude": .., "longitude": ..}, "radius_km": 2.0 }`

### A2.1 The request part (returns in milliseconds)

```
┌─ [UA] A-E1.0 · Start amenity search ────────────────────────────────────────────
│ in:   r1_run_id (from R1's reply / sessionStorage), origin, optional radius_km
│ do:   page shows SCREEN W, sends POST with credentials (cookie)
│ exit: ✔ request sent ──▶ G1 ──▶ G2
│ ⚠ A1 where the page gets `origin` from is outside this feature
│ ⚠ A2 no R2 run_id exists until the 202; a refresh in that window (milliseconds,
│      Iteration 2) leaves the page nothing to recover
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
┌─ [DATA] A-E1.2 · Read R1's finished output ────────── R1RunStore (NEW method, R2-P1) ──
│ in:   r1_run_id, user_id
│ do:   R1RunStore.get_finished_output(r1_run_id, user_id)   (one read, no second lookup)
│       SELECT output, workflow_version FROM r1_runs
│       WHERE run_id AND user_id AND status = "finished"     (only the column R2 needs)
│       decode output → category_metric_plans; workflow_version must match
│ exit: ✔ category_metric_plans ──▶ A-E1.3
│       ✖ None (missing, another user's, not finished, or finished before
│         the output column existed) ──▶ 404
│       ✖ workflow_version mismatch ──▶ 404 (output shape is unknown; start R1 again)
│       ✖ database error / timeout (10 s) ──▶ 503 "Run storage is unavailable"
│ ✅ R2-C6 "the R1 run must be the same user's and finished"
│ ✅ decided: no 409 path. The page only offers R2 after R1 is finished, so an
│    unfinished R1 reaching here is not designed for; the `finished` filter still
│    stops it, as a 404.
│ ✅ decided (R2-P1): R1 writes its final result to `r1_runs.output` in the same
│    UPDATE that sets `finished`; a CHECK makes `output` non-null iff `finished`.
│    No step rows are loaded and nothing is replayed here.
│ RULE  read is idempotent and has no retry; 503 means "try again", 404 means
│       "go back to R1". Same shared async client and 10 s timeout as R1.
└──────────────────────────────────────────────────────────────────────────────────
        │ category_metric_plans
        ▼
┌─ [DATA] A-E1.3 · Create the run ──────────────────────────────── R2-C4 + R2-C3 ──
│ in:   new run_id (created ONCE here), user_id, r1_run_id,
│       AmenitySearchState(origin, radius_km, category_metric_plans)     ✅ R2-C1
│ do:   INSERT r2_runs { run_id, user_id, r1_run_id, status:"running", attempts:0,
│                        completed_step:null, state: {version, state}, retryable:false }
│       run_id_var = run_id (every log line carries it)
│ exit: ✔ row exists ──▶ A-E1.3a
│       ✖ database error ──▶ 503 (no row, nothing to retry)
│ ✅ R2-C5: a working run is `running`, not R1's "failed, not retryable" placeholder
└──────────────────────────────────────────────────────────────────────────────────
        │ run_id, state, attempts = 0
        ▼
┌─ [BIZ] A-E1.3a · Start the background task ─────────────── R2-C6 Iteration 2 ──
│ in:   run_id, user_id, state, attempts = 0
│ do:   task = asyncio.create_task(coordinator.execute(run_id, user_id, state,
│                                  attempts=0, resume_after=None))
│       app.state.r2_tasks[run_id] = (task, user_id)
│       task.add_done_callback(→ remove run_id from r2_tasks)
│ exit: ✔ ──▶ A-E1.3b (the request part)   and   ──▶ A-E1.4 (the task)
│ ✅ R2-C6 Iteration 2 "the task set": a referenced task can't be garbage-collected
│    mid-run; the user_id is kept for the E3 ownership check (A-E3.0a)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [RESP] A-E1.3b · Accepted ───────────────────────────────────────────── R2-C7 ──
│ 202 { run_id, status:"running" }
│ [UA→] ──▶ A-E1.11 (save run_id, SCREEN W, poll E3)
│ The request ends here. A refresh or closed tab from now on never touches the run.
└──────────────────────────────────────────────────────────────────────────────────
```

### A2.2 The background part (seconds)

```
┌─ [BIZ] A-E1.4 · Step `discovery` ─────────────────── AmenitySearch.run_place_discovery ──
│ in:   state (origin, radius_km, category_metric_plans)
│       this run's AmenitySearch (built by the coordinator for this run, R2-C2 Iteration 1)
│ do:   per category, concurrently:  build request → searchNearby → canonical place set   PAID
│       each searchNearby: take a RUN slot (this run's semaphore, 3)
│                          then a GLOBAL slot (app-wide Places semaphore, 15)
│                          → call → release both
│       → state.discovered_places[category_id] = {place_id: CanonicalPlace}
│ exit: ✔ ──▶ A-E1.5
│       ✖ PlaceDiscoveryCallError     (provider)  ──▶ A-E1.9  retryable, unless the
│         config-error check finds a config cause (same helper as A-E1.6, R2-C6 Iteration 1)
│       ✖ PlaceDiscoveryRequestError  (bad plan)  ──▶ A-E1.9  not retryable
│ ✅ R2-C2 (method reused as-is; called by the coordinator's step list)
│ ✅ R2-C2 Iteration 1: per-run limit 3 + one global cap 15
│    · lifespan builds the Places client, the Routes client and the global
│      semaphore ONCE, keeps them on app.state and passes them to the coordinator
│    · each run gets a NEW AmenitySearch from those shared objects; its
│      constructor still makes its own semaphore of 3; it does not own the
│      shared clients (closing the run never closes them)
│    · result: one customer ≤ 3 Places calls in flight; the process ≤ 15
│    · run slot first, then global slot: a run waiting on its own limit never
│      holds a global slot, so at most 5 runs share the 15 at full speed
│ ⚠ A19 waiting for a global slot lengthens the run (the task, not a request)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [DATA] A-E1.5 · Checkpoint after discovery ────────────────────── SAVE · FENCE ──
│ in:   state with discovered_places
│ do:   1. UPDATE r2_runs SET state = R2-C3 JSON, completed_step = "discovery"
│          WHERE run_id AND user_id AND status = "running" AND attempts = <mine>
│       2. only if 1 matched, the step row (R2-C4 Iteration 1):
│          first run / reclaimed crash → insert_step: INSERT r2_run_steps
│                                        { run_id, "discovery", completed, output }
│          claimed retry step          → complete_claimed_step: started → completed
│          output = {schema_version, data: discovered_places}
│ exit: ✔ 1 row (+ step row saved) ──▶ A-E1.6
│       ✖ 0 rows (a newer execution owns the row) ──▶ log r2_run.superseded, stop,
│         NO step row (no reply: the request ended at A-E1.3b)
│       ✖ database error on 1 ──▶ A-E1.9 (save failed quietly; the row may stay
│                                 `running` ──▶ reclaimable after stale_after)
│       ✖ step row duplicate / claimed row moved ──▶ log r2_run.step_conflict, stop
│       ✖ database error on 2 ──▶ log only, carry on ──▶ A-E1.6 (run row is right) ⚠ A24
│ ✅ R2-C2 table: discovery is costly + non-reproducible + external work follows
│ ✅ R2-C4 Iteration 1: run row first, step row second; the run row decides resume
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] A-E1.6 · Step `enrichment` ─────────── AmenitySearch.run_accessibility_enrichment ──
│ in:   state.discovered_places
│ do:   unique place index (drop places with no location)
│       concurrently: routing re-search per category × mode (walk/drive/cycle)   PAID
│                     transit matrix per ≤100 places                              PAID
│       (routing re-search takes the same run slot + global slot as A-E1.4;
│        the transit matrix takes only this run's Routes semaphore of 3)
│       → state.enrichment[place_id] = EnrichmentBundle
│       (no place with a location → returns early; counts as completed)
│ exit: ✔ ──▶ A-E1.7   (NO save here; the `enrichment` step row waits for A-E1.8)
│       ✖ RoutingRetrievalError / TransitRetrievalError ──▶ A-E1.9, retryable decided
│         by the coordinator's config-error check (R2-C6 Iteration 1):
│           follow __cause__ down to Google's original error
│             RoutingRetrievalError / TransitRetrievalError   ← coordinator sees
│               └─ PlacesClientError / RoutesClientError
│                    └─ google_exceptions.<X>                  ← real reason
│           X ∈ {InvalidArgument, FailedPrecondition, PermissionDenied}
│             ──▶ config error: retryable = false, log r2_run.config_error ──▶ SCREEN S
│           anything else (timeout, unavailable, rate limit, …)
│             ──▶ provider failure: retryable = true (while attempts < MAX) ──▶ SCREEN F
│ ✅ R2-C6 Iteration 1: one helper, R2's code unchanged; covers a Routes API that is
│    disabled or not allowed for the key, which passes discovery and fails here
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
│ ✅ R2-C2 (pure, covered by the finish write); no step row (pure step, as R1)
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
│ then, only if it matched, step row:        │  │ then, only if it matched, step row for the     │
│   "enrichment" completed, output =         │  │ step that was running (R2-C4 Iteration 1):     │
│   {schema_version, data: enrichment}       │  │   discovery / enrichment → save_step_failed    │
│   (insert_step, or complete_claimed_step   │  │     { error_type, error_message, retryable =   │
│    for a claimed retry step)               │  │       the run's }  (insert, or started→failed  │
│   enrichment returned early (no place      │  │       for a claimed step)                      │
│   located) → still a completed row         │  │   attachment / no step running → no step row   │
│ ✔ ──▶ A-E1.10a                             │  │ ✔ / store down (logged only) ──▶ A-E1.10b      │
│ ✖ 0 rows ──▶ superseded (log only),        │  │ ✅ R2-C4 "save as failed never touches state"  │
│   no step row                              │  │ store down → row stays running                 │
│ ✖ db error ──▶ log; row stays running      │  │   ──▶ reclaimable after stale_after            │
│   ──▶ reclaimable after stale_after        │  │ step row error ──▶ log only (⚠ A24)            │
│ ✖ step row error ──▶ log only (⚠ A24)      │  │                                                │
│ ✅ R2-C4 output column for R3              │  │                                                │
└────────────────────────────────────────────┘  └────────────────────────────────────────────────┘
        │                                            │
        ▼                                            ▼
┌─ [BG] A-E1.10a · Saved to the row ─────────┐  ┌─ [BG] A-E1.10b · Saved to the row ─────────────┐
│ row: status finished, completed_step       │  │ row: status failed, failure_stage, retryable   │
│      "discovery", output with              │  │ (provider unavailable / other R2 error /       │
│      predefined_records                    │  │  unexpected are kept as failure_stage; the     │
│ NO reply: the page reads it through E3     │  │  502/503/500 codes no longer reach the page)   │
│ task ends ──▶ removed from r2_tasks        │  │ task ends ──▶ removed from r2_tasks            │
│ (after the save, never before)             │  │ (after the save, never before)                 │
└────────────────────────────────────────────┘  └────────────────────────────────────────────────┘
        │                                            │
        └──────────────────────┬─────────────────────┘
                               ▼ (next E3 poll)
┌─ [UA→] A-E1.11 · Save the run_id, start polling ────────────────────────────────
│ on the 202 (A-E1.3b): save run_id in sessionStorage ──▶ SCREEN W
│ poll E3 every ~2 s while status is running (A4)
│ finished                ──▶ SCREEN R2 (render predefined_records)
│ failed, retryable:true  ──▶ SCREEN F "Retry" (──▶ E2)
│ failed, retryable:false ──▶ SCREEN S "Start again" (new E1)
│ ✅ R2-C7 "refresh recovery"
└──────────────────────────────────────────────────────────────────────────────────
```

**Shutdown during A2.2** (deploy, restart): `lifespan` cancels each task in `r2_tasks` and
awaits it (short timeout), **before** it closes the shared Places and Routes clients.
`CancelledError` lands at the current `await`, and the task saves the run as failed with
`retryable = attempts < MAX` (best effort), then re-raises. A client leaving never cancels the
task. ✅ R2-C6 table, R2-C6 Iteration 2 "shutdown rule" (⚠ A21)

**A-E1 exits at a glance**

Request part (the HTTP reply to E1):

| Exit | HTTP | Row after it | Screen next |
|---|---|---|---|
| Not logged in / token expired | 401 | none | login, or refresh then resend |
| Bad origin / radius / body | 422 | none | fix input |
| R1 run missing, another user's, or not finished | 404 | none | SCREEN R1 / start again |
| Database down before the row | 503 | none | try again later |
| Row created, task started | 202 | `running`, `completed_step=null` | SCREEN W, poll E3 |

Background part (no HTTP reply; the page sees the row through E3):

| Outcome | Row after it | Screen next (via E3) |
|---|---|---|
| Finished | `finished`, `completed_step=discovery`, state + output | SCREEN R2 |
| Places/Routes failure in discovery | `failed`, `retryable:true`, `completed_step=null` | SCREEN F |
| Places/Routes failure in enrichment | `failed`, `retryable:true`, `completed_step=discovery` | SCREEN F |
| Config error in discovery or enrichment (bad key, API off, request rejected) | `failed`, `retryable:false`, logs `r2_run.config_error` | SCREEN S |
| Bad plan (request / assembly error) | `failed`, `retryable:false` | SCREEN S |
| Unexpected error | `failed`, `retryable:false`, stage `unexpected` | SCREEN S |
| Shutdown mid-run | `failed`, `retryable = attempts < MAX` | SCREEN F (or S if the retry was used) |
| Lost fence | owned by the newer execution (log only) | whatever the newer execution saves |

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
│ do:   SELECT r2_runs WHERE run_id AND user_id, with its r2_run_steps rows embedded
│       (as R1's load_run); decode state + version check
│ exit: ✔ status, retryable, attempts, completed_step, updated_at, state,
│         step rows ──▶ A-E2.2
│       ✖ step rows missing from the reply ──▶ 503 (fail loudly, as R1)
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
│       then, if the step the retry resumes at has a `failed` row
│       (discovery when completed_step = null, else enrichment):
│         claim_failed_step: UPDATE r2_run_steps SET status = "started", error cleared
│         WHERE run_id AND step_id AND status = "failed"
│       (a stale-reclaimed crash has no failed row: nothing to claim; the step is
│        inserted as new at its write point)
│ exit: ✔ 1 row (+ step claimed, or nothing to claim) ──▶ A-E2.4
│         (this execution's fence value is now n + 1)
│       ✖ 0 rows ──▶ 409 "Another retry of this run already started"; runs nothing
│       ✖ step row moved ──▶ set run failed, not retryable ──▶ 409 "start again"
│         (as R1's step_conflict)
│ ✅ R2-C5 Approach 2 · same shape as R1's mark_retry_started
│ ✅ R2-C5 "step-row claim" (R2-C4 Iteration 1)
│ ⚠ A6 the OR of two conditions has to be expressed through supabase-py / PostgREST
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] A-E2.4 · Start the resumed task, reply 202 ─────── R2-C2 + R2-C6 Iteration 2 ──
│ in:   state from A-E2.1, completed_step, fence n + 1
│ do:   task = create_task(coordinator.execute(run_id, user_id, state,
│                          attempts = n + 1, resume_after = completed_step))
│       app.state.r2_tasks[run_id] = (task, user_id)   (removed by the done callback)
│ exit: ✔ ──▶ 202 { run_id, status:"running", completed_step } ──▶ SCREEN W (polls E3)
│ background (A2.2 boxes, every write with FENCE attempts = n + 1):
│       completed_step = null        → A-E1.4 discovery → A-E1.5 SAVE → A-E1.6 → A-E1.7
│       completed_step = "discovery" → A-E1.6 enrichment → A-E1.7          (discovery NOT rerun)
│   the claimed step row completes at its write point (A-E1.5 / A-E1.8, started → completed)
│   or fails again (A-E1.9, started → failed)
│   outcome ──▶ A-E1.8 finished, or A-E1.9 failed with retryable:false (limit used)
│             lost fence ──▶ log only
│   the page sees the outcome through E3
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
| Run claimed but its failed step row moved | 409 | `failed`, `retryable:false` | SCREEN S |
| Claimed, task started | 202 | `running`, `attempts=n+1` | SCREEN W, poll E3 |
| Background: finished | — (via E3) | `finished`, state + output | SCREEN R2 |
| Background: fails again | — (via E3) | `failed`, `retryable:false` | SCREEN S |

---

## A4 — E3 · Status (refresh recovery)

**Purpose.** Poll a running run, and after a refresh or a `409`, show the screen that matches the
saved run without doing any work.

**Endpoint.** `GET /api/amenity-search/runs/{run_id}`

```
┌─ [UA] A-E3.0 · Poll / page load / resync ───────────────────────────────────────
│ do:   every ~2 s while status is running; also on page load (sessionStorage)
│ exit: ✔ found ──▶ GET ──▶ G1 ──▶ G2      ✖ not found ──▶ SCREEN R1
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] A-E3.0a · In-memory check (no I/O) ───────────────── R2-C6 Iteration 2 ──
│ do:   look up run_id in app.state.r2_tasks
│ exit: ✔ found, same user_id    ──▶ 200 { run_id, status:"running" } (no DB read)
│                                    ──▶ SCREEN W, poll again
│       ✖ found, another user's   ──▶ 404 (same answer as the DB read would give) ⚠ A23
│       ✔ not found               ──▶ A-E3.1 (finished, failed, crashed, or another process)
│ ⚠ A22 per process: a run started by another worker is only found by A-E3.1
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
│              RULE the page polls again in ~2 s
│ finished ──▶ 200 { run_id, status, completed_step, result }    ──▶ SCREEN R2 (stop polling)
│ failed   ──▶ 200 { run_id, status, completed_step, retryable } ──▶ SCREEN F or S (stop polling)
│ ⚠ A5 a `running` row that is already stale (crashed) still reads as `running`
└──────────────────────────────────────────────────────────────────────────────────
```

---

## A5 — The R2 run row: lifecycle and data actions

### A5.1 Status lifecycle

```
   (no row) ── 422 / 404 / 503 before the row ──▶ (still no row)
      │
      │ A-E1.3 INSERT                    attempts = 0, completed_step = null
      │ A-E1.3a task started, 202 sent   (everything below happens in the task)
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
   Shutdown ──▶ lifespan cancels the task ──▶ failed (retryable = attempts < MAX).
   While the task is live, E3 answers `running` from r2_tasks without reading the row.

   Step rows (r2_run_steps, R2-C4 Iteration 1), one per (run_id, step_id), for discovery and
   enrichment only:
      (none) ──insert_step──▶ completed            (never changes again: trigger)
      (none) ──save_step_failed──▶ failed ──claim_failed_step──▶ started
                                                     ├─complete_claimed_step─▶ completed
                                                     └─save_step_failed────▶ failed
   They record each step; they never decide resume or status (the run row does).
```

### A5.2 Data actions per endpoint, in order

| # | Endpoint | Store operation (R2-C4) | Columns written | Filter |
|---|---|---|---|---|
| 1 | E1 | (R1) Get the finished output (R2-P1) | — (read `r1_runs.output`, `workflow_version`) | `r1_run_id`, `user_id`, `finished` |
| 2 | E1 | Create a run | all initial columns, `status=running` | — (insert) |
| 3 | E1 | Save a checkpoint | `state`, `completed_step=discovery` | `running`, `attempts=n` |
| 3s | E1 | Insert step (`discovery`), only if 3 matched | `r2_run_steps`: `completed`, `output` | — (insert; duplicate key = conflict) |
| 4 | E1 | Save as finished | `status`, `state`, `output`, `retryable=false` | `attempts=n` |
| 4s | E1 | Insert step (`enrichment`), only if 4 matched | `r2_run_steps`: `completed`, `output` | — (insert; duplicate key = conflict) |
| 4' | E1 | Save as failed | `status`, `failure_*`, `retryable` | `attempts=n` |
| 4's | E1 | Save step failed (step that was running), only if 4' matched | `r2_run_steps`: `failed`, `error_*`, `retryable` | — (insert) |
| 5 | E2 | Load a run, with its step rows | — (read) | `run_id`, `user_id` |
| 6 | E2 | Claim for retry | `status=running`, `attempts=n+1`, `retryable=false` | `attempts=n` + (failed∧retryable ∨ running∧stale) |
| 6s | E2 | Claim the failed step, if any | `r2_run_steps`: `failed → started`, error cleared | `run_id`, `step_id`, `status=failed` |
| 7 | E2 | Checkpoint / finished / failed | as 3 / 4 / 4'; the claimed step row moves `started → completed` or `started → failed` | `attempts=n+1`; step row `status=started` |
| 8 | E3 | Load a run (skipped while the task is in `r2_tasks` for this user) | — (read) | `run_id`, `user_id` |
| 9 | R3 | Get the finished output | — (read `output`) | `finished` |

Every read and write on `r2_runs` filters on `run_id` **and** `user_id`. `r2_run_steps` has no
`user_id` (as `r1_run_steps`): its writes come only after a matched `r2_runs` write for this
user, and its reads are embedded in that user's `r2_runs` read. Every write is one single-row
statement. ✅ R2-C4, R2-C4 Iteration 1

### A5.3 Paid calls per path (cost and wait time on SCREEN W)

With `C` categories and `P` distinct places (≤ 10 per category):

| Path | Places / Routes calls per run (in the background task) |
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
| A2 | A-E1.0 | The run ID reaches the page only with the reply. A refresh during the start request leaves the page with nothing to recover, as in R1's B2. | ✅ mostly resolved (R2-C6 Iteration 2): the `202` comes back in milliseconds, so the window is tiny (as R3's B9) |
| A5 | A-E3.2 | After a hard crash, the row stays `running`. For up to `stale_after` (10 min) the page shows "waiting", and retry returns `409 running`. The page can't tell a live run from a dead one, because the status reply carries no "stale" signal. | ⚠ open: add `retryable:true` to a stale `running` reply, or let the page offer Retry after a timeout |
| A8 | A-E1.10b | A non-retryable failure (bad plan) can only be fixed upstream in R1. The customer sees "Start again" for R2, but starting R2 again with the same R1 run fails the same way. | ⚠ open: the page should send the customer back to R1 |
| A9 | A5.1 | Two R2 runs for the same R1 run are allowed. Each costs a full set of Places calls. | ✅ decided (R2-C6), cost note only |

### A7.2 Technical level (what the code must handle)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| A3 | A-E1.6 / A-E2.4 | Enrichment re-searches Places per category and mode, and joins by `place_id`. On a resume, it runs long after the saved discovery, so the re-search can return different places. Places missing from it get all-null routing (an existing WARN). The logic is unchanged, but the gap widens. | ✅ accepted (logic unchanged); shows as `attachment.accessibility_degraded` |
| A4 | A-E1.4–A-E1.7 | Whether a client disconnect cancels the handler (`log_requests` is an `http` middleware) wasn't known. If it did, the run would be saved as failed and retryable. | ✅ resolved: Starlette 1.6 doesn't cancel the handler on disconnect, and since R2-C6 Iteration 2 the run doesn't depend on the handler |
| A6 | A-E2.3 | The claim needs `attempts = n AND ((failed ∧ retryable) ∨ (running ∧ updated_at < cutoff))` in one statement. supabase-py supports `.or_()` with nested `and(...)`, but the timestamp format and escaping need care. The fallback is two conditional updates tried in order, each still atomic. | ⚠ implementation detail; R2-C8 "concurrent retries" proves it |
| A10 | A-E1.5 / A-E1.8 | The database is down after paid work succeeded. A checkpoint failure loses discovery. A finish failure loses enrichment, but discovery is saved. Either way the row stays `running`, becomes stale after 10 min and can be reclaimed. | ✅ covered by R2-C5 (cost of the lost step only) |
| A11 | A-E1.9 | The cancellation row in the R2-C6 table says "Yes" (retryable) without repeating the retry limit. This traceflow applies `attempts < MAX`, so a cancelled retry becomes not retryable. | ✅ aligned: the R2-C6 cancellation row now reads "Yes, while `attempts < MAX_RETRY_ATTEMPTS`" |
| A17 | A-E1.2 | R1 runs that finished before the `output` column existed have `output = null`, so R2 can't start from them. | ✅ decided (R2-P1): they read as `404`; the customer starts R1 again. No backfill |
| A18 | A-E1.2 | If R1 set `finished` and wrote `output` in two writes, a crash between them would leave a finished run with no output. | ✅ decided (R2-P1): one UPDATE writes both, and the CHECK constraint rejects any other combination |
| A20 | A-E1.4 / A-E1.6 | R2 wraps every Google error in its own type, so a bad key and a Google outage both arrive as `PlaceDiscoveryCallError` / `RoutingRetrievalError` / `TransitRetrievalError`. Both were marked retryable, so the customer got a Retry that couldn't work. | ✅ decided (R2-C6 Iteration 1): the coordinator follows `__cause__` to Google's error; `InvalidArgument`, `FailedPrecondition`, `PermissionDenied` → not retryable + `r2_run.config_error` |
| A21 | A-E1.4–A-E1.9 | Shutdown during a run: `lifespan` cancels the task and waits a short time for its "save as failed". If the timeout is hit first, the row stays `running`. The tasks must also be cancelled before the shared Places/Routes clients close, or a task fails on a closed client instead. | ✅ decided (R2-C6 Iteration 2): cancel and await tasks first, then close clients; a missed save is covered by stale reclaim (as B14) |
| A22 | A-E3.0a | The in-memory check only sees this process's tasks. A run in another worker, or one lost in a crash, is answered from the row. | ✅ accepted for MVP (one process); the fallback is the database read, so it is correct, only slower |
| A23 | A-E3.0a | The memory check answers before the database, so it must check ownership itself, or another user's `run_id` would get `running`. | ✅ decided: the set keeps `user_id`; a mismatch gives `404`; tested in R2-C8 |
| A24 | A-E1.5 / A-E1.8 / A-E1.9 | The run write and the step write are two statements. A crash or a store error between them leaves the run row right but the step row missing. | ✅ accepted (R2-C4 Iteration 1): the step table is a record only; resume and status read `r2_runs` |
| A12 | A-E2.1 | The pre-check reads `updated_at` written by the database trigger (`clock_timestamp()`), and the cutoff is computed from the backend clock. Clock skew shifts staleness by the skew. | ✅ accepted (R2-C5: value ≫ skew) |

### A7.3 Architectural level (how the pieces fit)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| A13 | A-E1.4–A-E1.8 | R2 ran inside the request. More categories or slower Places responses would lengthen it, and nothing alerted when it neared proxy timeouts. | ✅ resolved (R2-C6 Iteration 2): the run is a background task, so no request stays open and there is no proxy timeout risk |
| A19 | A-E1.4 / A-E1.6 | The global cap of 15 is per process and covers Places calls only (discovery and the routing re-search, which share the Places semaphore). With several workers the real cap is 15 × workers, and the Routes transit matrix keeps only its per-run limit of 3. A 6th busy run waits for global slots, which lengthens the run. | ✅ accepted for MVP (one process, low traffic); revisit with more workers or Places `429`s |
| A14 | R2-C4 | The service-role key bypasses RLS. Isolation depends on every query adding `user_id`. | ✅ accepted, as R1; tested in R2-C8 |
| A15 | R2-C3 | The saved state is tied to `R2_STATE_SCHEMA_VERSION`. A deploy that changes `AmenitySearchState` fails in-flight runs as not retryable. | ✅ accepted, as R1 |
| A16 | R2-C4 | Google Places content is kept in `state` / `output` with no expiry, and since R2-C4 Iteration 1 also in the `discovery` and `enrichment` step rows. | ✅ decided: kept for now in both tables; the policy comes in a later phase |

### A7.4 Where to look first

1. **A5:** a crashed run looks alive for up to 10 minutes.
2. **A6:** the claim statement has to be truly one atomic update.
3. **A11:** the retry limit on cancellation.
4. **A21:** the shutdown order (cancel tasks, then close the clients).

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
                 404 no finished ◀───┬─────┴───── 202 { run_id, status:"running" } (immediately)
                 R2 output for user  │                     │
                                     │                     ▼
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
(not a UUID, or any other field in the body → `422` at G2; ✅ R3-C8 "Models")

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
│ do:   R2RunStore.get_finished_output(r2_run_id, user_id)   (one read, no second lookup)
│ exit: ✔ { category_metric_plans, discovered_places, predefined_records } ──▶ B-E1.2
│       ✖ None (missing, another user's, or not finished) ──▶ 404
│       ✖ StateVersionMismatchError (R2 output saved under another version)
│         ──▶ 404, log r3_run.rejected reason=r2_version_mismatch
│       ✖ database error ──▶ 503
│ ✅ R3-C7 "checked before the row is created"; "the R2 input saved under another version"
│ ✅ decided: no 409 path. The page only offers R3 after R2 is finished, so an
│    unfinished R2 reaching here is not designed for; the `finished` filter still
│    stops it, as a 404.
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
│ do:   run_id_var = run_id            (BEFORE create_task: the task inherits it)
│       task = asyncio.create_task(execute(run_id, user_id, state, attempts=0,
│                                          resume_after=None))
│       app.state.r3_tasks[run_id] = (task, user_id, completed_step=None)
│       done callback: remove the entry only if it still holds THIS task
│ exit: ✔ ──▶ B-E1.4
│ ✅ R3-C7 "keeping tasks alive", R3-C7 Iteration 2 (dict keyed by run_id)
│ ✅ R3-C3 run_id_var set before create_task
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
│       (run_id_var already set by B-E1.3 / B-E2.4)
│ do:   r3 = create_specific_metric_resolution(settings, llm_caller=shared,
│                                              app-wide provider limits)
│            → NEW McpToolGateway for this run only; owns_caller = False
│            → its own slots (Parallel 4, Firecrawl 2) + the APP-WIDE ones:
│              Parallel search slots (10), Firecrawl slots (2),
│              Firecrawl rate limiter (10/min, replaces the gateway's own bucket)
│       step tracking: in_flight = discovery_batch until the STEP 3 callback
│                      (resume after discovery_batch → in_flight = pipelines);
│                      a gateway / capability / catalog error gets no step row
│ exit: ✔ ──▶ B-BG.1
│ ✅ R3-C2 one instance per run (a shared gateway would be closed by another run's finally)
│ ✅ R3-C2 Iteration 1 one app-wide limit per provider, behind the run's own limit
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-BG.1 · r3.run_specific_metric_resolution(state, resume_after, on_step_completed) ──
│ ┌─ unchanged method body (inside view: R3_M1_Traceflow.md) ─────────────────────────────┐
│ │ caller check · breaker = new _CircuitBreaker(threshold)        (fresh on every attempt)│
│ │ gateway.open()   Parallel + Firecrawl sessions, capability check                       │
│ │   ✖ McpConnectionError: retryable, unless its __cause__ chain holds a 401 / 403        │
│ │     (refused key) ──▶ not retryable, log r3_run.config_error   (R3-C7 Iteration 1)     │
│ │   ✖ McpToolUnavailableError (not retryable)                                            │
│ │ every web call in STEP 3 / STEP 4, per provider:                                       │
│ │   Parallel search:  run slot → app-wide search slot → timeout → call                   │
│ │   Firecrawl call:   app-wide rate token → run slot → app-wide Firecrawl slot           │
│ │                     → timeout → call                                                   │
│ │   (a Parallel call never waits on a Firecrawl slot; waits stay outside the timeout)    │
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
│ ⚠ B27 waiting for an app-wide slot makes STEP 3 / STEP 4 longer (counts toward stale_after)
└──────────────────────────────────────────────────────────────────────────────────
        │ (called from inside STEP 3's barrier)
        ▼
┌─ [DATA] B-BG.2 · Checkpoint after STEP 3 (the callback) ──────────── SAVE · FENCE ──
│ in:   step = "discovery_batch", state, breaker_open
│ do:   breaker_open = true  ──▶ NO checkpoint (verdicts are outage-made `none`)  ✅ R3-C3
│                               completed_step stays null
│                               save_step_degraded right away: `discovery_batch`
│                               degraded with STEP 3's data (insert, or started →
│                               degraded for a claimed step)
│       breaker_open = false ──▶ 1. UPDATE r3_runs SET state = R3-C4 JSON,
│                                      completed_step = "discovery_batch"
│                                   WHERE run_id AND user_id AND status = running
│                                     AND attempts = n
│                                2. only if 1 matched, the step row (R3-C5 Iteration 1):
│                                   first run / reclaimed crash → insert_step:
│                                     { run_id, "discovery_batch", completed, output }
│                                   claimed retry step → complete_claimed_step:
│                                     started → completed
│                                   output = {schema_version, data: STEP 3's three
│                                             result dicts, tuple keys encoded}
│                                3. r3_tasks[run_id].completed_step = "discovery_batch"
│       in_flight = pipelines (from here on, an error is recorded on `pipelines`)
│ exit: ✔ saved / skipped ──▶ back into B-BG.1 (STEP 4 starts)
│       ✖ 0 rows on 1 ──▶ raise RunSupersededError (leaves the method through its finally)
│       ✖ db error on 1 ──▶ raise RunStoreError    (same path; saved as stage run_store)
│       ✖ step row duplicate / claimed row moved ──▶ log r3_run.step_conflict, stop
│       ✖ db error on 2 ──▶ log r3_run.step_record_failed, carry on (run row is right)
│ ✅ R3-C3 table: STEP 3 is costly + non-reproducible + STEP 4 follows
│ ✅ R3-C5 Iteration 1: run row first, step row second; the run row decides resume
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
│ failure_stage, failure_message = null      │  │   state, completed_step UNTOUCHED              │
│ then, only if it matched, step rows:       │  │ then, only if it matched, step rows:           │
│   "pipelines" completed, output =          │  │   in_flight step → save_step_failed            │
│   {schema_version, data:                   │  │     { error_type, error_message, retryable =   │
│    resolution_results}  (insert_step, or   │  │       the run's }  (insert, or started→failed  │
│    complete_claimed_step if claimed)       │  │       for a claimed step)                      │
│ ✖ 0 rows ──▶ superseded (log), no row      │  │   setup error / nothing in flight → no row     │
│ ✖ db error ──▶ B-BG.4, stage run_store     │  │ store down → log r3_run.failed_not_saved;      │
│   (retryable while attempts < MAX)         │  │   row stays running                            │
│ ✖ step row error ──▶ log only              │  │   ──▶ reclaimable after stale_after            │
│ ✅ R3-C5 "finish clears failure fields"    │  │ step row error ──▶ log only                    │
└────────────────────────────────────────────┘  └────────────────────────────────────────────────┘
        │                                             │
        └───────────────────────┬─────────────────────┘
                                ▼
┌─ [BG] B-BG.5 · Task end ─────────────────────────────────────────────── R3-C7 ──
│ finally: await r3.aclose()   (this run's gateway; shared caller NOT closed;
│                               app-wide provider limits NOT closed)
│          done callback: remove app.state.r3_tasks[run_id] only if it still holds
│          THIS task (a reclaimed run may have a newer entry); always AFTER the save
│          a non-cancel exception left the task ──▶ log r3_run.task_crashed (ERROR)
│ The page sees the outcome only through E3.
│ ✅ R3-C7 Iteration 2 "removal", "order"
└──────────────────────────────────────────────────────────────────────────────────
```

**Shutdown during B-BG.1** (deploy, restart): `lifespan` first calls the R3 coordinator's
`shutdown()`. It cancels each task in `r3_tasks` and awaits them, with R3's own timeout
(`R3_SHUTDOWN_TIMEOUT_SECONDS = 10`). `CancelledError` lands at the current `await`. The method's
`finally` closes the run's gateway, then the task saves the run as failed with stage `cancelled`
and `retryable = attempts < MAX`, best effort, and re-raises. Only after that does `lifespan` close the
shared LLM caller and the database client. A timeout logs `r3_run.shutdown_timeout` with the
pending run IDs; those rows stay `running` and are reclaimable. ✅ R3-C7 "shutdown"

**B-E1 / background outcomes at a glance**

| Outcome | HTTP (E1) | Row after it | Step rows (R3-C5 Iteration 1) | E3 shows | Screen |
|---|---|---|---|---|---|
| Body not a UUID / extra field | 422 | none | none | — | fix input |
| R2 run missing, another user's, not finished, or another output version | 404 | none | none | — | SCREEN R2 |
| Database down before the row | 503 | none | none | — | try later |
| Accepted | 202 | `running` | none yet | `running`, `completed_step` (from memory) | SCREEN P |
| Finished | (202 earlier) | `finished`, state + output | `discovery_batch` + `pipelines` completed | `result` | SCREEN R3 |
| Gateway can't connect | (202) | `failed`, `retryable:true`, `completed_step=null` | none | `retryable:true` | SCREEN F |
| Gateway key refused (401 / 403 on the cause chain) | (202) | `failed`, `retryable:false`, logs `r3_run.config_error` | none | `retryable:false` | SCREEN S |
| Breaker open / provider down in STEP 4 | (202) | `failed`, `retryable:true`, `completed_step=discovery_batch` *if STEP 3 was clean* | `discovery_batch` completed, `pipelines` failed | `retryable:true` | SCREEN F |
| Breaker opened during STEP 3 | (202) | `failed`, `retryable:true`, `completed_step=null` (no checkpoint) | `discovery_batch` degraded (with data), `pipelines` failed | `retryable:true` | SCREEN F |
| Database error on the checkpoint or finish write | (202) | `failed`, stage `run_store`, `retryable:true` | the running step failed | `retryable:true` | SCREEN F |
| Catalog / tool missing | (202) | `failed`, `retryable:false` | none | `retryable:false` | SCREEN S |
| Unexpected error | (202) | `failed`, `retryable:false`, stage `unexpected` | the running step failed | `retryable:false` | SCREEN S |
| Shutdown mid-run | (202) | `failed`, stage `cancelled`, `retryable = attempts < MAX` (best effort) | the running step failed | `retryable` | SCREEN F (or S if the retry was used) |
| Hard crash | (202) | stays `running` | none for the running step | `running` until stale | SCREEN P (⚠ B5) |

---

## B3 — E2 · Retry an R3 run

**Purpose.** Continue a failed or crashed run from its last saved step, in the background, with
one execution live at a time.

**Endpoint.** `POST /api/specific-metric-resolution/runs/{run_id}/retry` · no body

```
┌─ [UA] B-E2.0 · Click Retry ── POST, no body ──▶ G1 ──▶ G2 ─────────────────────────────
        ▼
┌─ [DATA] B-E2.1 · Load the run ────────────────────────────────── R3-C5 + R3-C4 ──
│ do:   SELECT r3_runs by run_id + user_id, with its r3_run_steps rows embedded
│       (as R2's load_run); decode state (tuple keys rebuilt) + version
│ exit: ✔ ──▶ B-E2.2    ✖ 404    ✖ version mismatch ──▶ save failed, not retryable ──▶ 409
│       ✖ step rows missing from the reply ──▶ 503 (fail loudly, as R2)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-E2.2 · Retry pre-check ───────────────────────────────────────── R3-C6 ──
│ same rules as A-E2.2, with stale_after = 30 min
│ exit: ✔ ──▶ B-E2.3      ✖ ──▶ 409 { run_id, status, retryable }
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] B-E2.3 · Claim the run (THE guard) ───────────────────────────── R3-C6 ──
│ same single conditional UPDATE as A-E2.3, on r3_runs
│ then claim_step on every step row at or after the resume step that is
│ `failed` or `degraded` (resume step = discovery_batch when completed_step = null,
│ else pipelines):
│   UPDATE r3_run_steps SET status = "started", error and output cleared
│   WHERE run_id AND step_id AND status IN ("failed", "degraded")
│   (a stale-reclaimed crash has no such row: nothing to claim; the step is
│    inserted as new at its write point)
│ exit: ✔ 1 row (+ rows claimed, or nothing to claim) ──▶ B-E2.4 (fence n + 1)
│       ✖ 0 rows ──▶ 409 "Another retry … already started"
│       ✖ a step row moved ──▶ set run failed, not retryable ──▶ 409 "start again"
│ ✅ R3-C6; R3-C5 Iteration 1 `claim_step` (degraded is claimed like failed)
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-E2.4 · Schedule the resumed task ─────────────────────────────── R3-C7 ──
│ do:   run_id_var = run_id   (before create_task)
│       create_task(execute(run_id, user_id, state, attempts = n + 1,
│                           resume_after = completed_step))
│       app.state.r3_tasks[run_id] = (task, user_id, completed_step from the row)
│ exit: ✔ ──▶ 202 { run_id, status:"running", completed_step } ──▶ SCREEN P (polls E3)
│ background: B-BG.0 → B-BG.1 with resume_after:
│     null              → STEP 3 runs (checkpointed if clean, degraded row if not) → STEP 4
│     "discovery_batch" → STEP 3 SKIPPED → STEP 4        (STEP 3 calls made once in total)
│   claimed rows complete at their write point (B-BG.2 / B-BG.3, started → completed),
│   or go started → failed / degraded at B-BG.4
│   outcome ──▶ B-BG.3 / B-BG.4 with FENCE n + 1; a failure now is retryable:false
│ ✅ R3-C3 resume rule; R3-C9 "resume parity"
└──────────────────────────────────────────────────────────────────────────────────
```

**B-E2 exits at a glance**

| Exit | HTTP | Row after it | Screen next |
|---|---|---|---|
| Run missing or another user's | 404 | unchanged | SCREEN S |
| Version mismatch | 409 | `failed`, `retryable:false` | SCREEN S |
| Finished / not retryable / limit used | 409 | unchanged | SCREEN R3 or S |
| Still running, not stale | 409 `status:running` | unchanged | keep polling E3 |
| Lost the claim to another request | 409 | owned by the winner | call E3 |
| Run claimed but a step row moved | 409 | `failed`, `retryable:false` | SCREEN S |
| Claimed, task started | 202 | `running`, `attempts=n+1` | SCREEN P, poll E3 |
| Background: finished | — (via E3) | `finished`, state + output | SCREEN R3 |
| Background: fails again | — (via E3) | `failed`, `retryable:false` | SCREEN S |

---

## B4 — E3 · Status (polling and refresh recovery)

**Endpoint.** `GET /api/specific-metric-resolution/runs/{run_id}`

```
┌─ [UA] B-E3.0 · Poll / page load ────────────────────────────────────────────────
│ do:   every few seconds while status is running; also on page load (sessionStorage)
│ exit: ✔ ──▶ G1 ──▶ G2
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] B-E3.0a · In-memory check (no I/O) ───────────────── R3-C7 Iteration 2 ──
│ do:   look up run_id in app.state.r3_tasks
│ exit: ✔ found, same user_id ──▶ 200 { run_id, status:"running", completed_step }
│                                 (completed_step from the entry: set only after the
│                                  STEP 3 checkpoint write matched) ──▶ SCREEN P
│       ✖ found, another user's ──▶ 404 (same answer as the DB read would give)
│       ✔ not found ──▶ B-E3.1 (finished, failed, crashed, or another process)
│ ⚠ B28 per process: a run started by another worker is only found by B-E3.1
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
   (no row) ── 404 / 503 before the row ──▶ (still no row)
      │
      │ B-E1.2 INSERT                       attempts = 0, completed_step = null
      ▼
   running ──B-BG.2 SAVE (breaker closed)──▶ running (completed_step = discovery_batch) ──B-BG.3──▶ finished
      │      B-BG.2 NO CHECKPOINT (breaker open) ──▶ running (completed_step = null)    ──B-BG.4──▶ failed
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

**Step-row lifecycle** (`r3_run_steps`, a record only; the run row above decides resume and
status). ✅ R3-C5 Iteration 1

```
   discovery_batch:
     (no row) ──B-BG.2 checkpoint matched──────────────────▶ completed   (never changes again)
     (no row) ──breaker open at B-BG.2, written at once──▶ degraded    (holds STEP 3's data)
     (no row) ──error in STEP 3, B-BG.4 matched────────────▶ failed
     degraded / failed ──B-E2.3 claim──▶ started (error + output cleared)
     started ──B-BG.2 checkpoint──▶ completed     started ──breaker open again──▶ degraded
     started ──error, B-BG.4──▶ failed

   pipelines:
     (no row) ──B-BG.3 finish matched───▶ completed      (never written before the finish write)
     (no row) ──error after the STEP 3 callback, B-BG.4──▶ failed
     failed ──B-E2.3 claim──▶ started ──B-BG.3──▶ completed   /  ──B-BG.4──▶ failed

   no row ever for: a gateway / capability / catalog error, a lost fence, a hard crash
   a claimed row the retry never reaches stays started (record only, accepted)
```

### B5.2 Data actions per endpoint, in order

| # | Where | Store operation (R3-C5) | Columns written | Filter |
|---|---|---|---|---|
| 1 | E1 | (R2) Get the finished output | — (read `r2_runs.output`) | `r2_run_id`, `user_id`, `finished` |
| 2 | E1 | Create a run | initial columns, `status=running` | — (insert) |
| 3 | BG | Save a checkpoint (only if breaker closed) | `state`, `completed_step=discovery_batch` | `running`, `attempts=n` |
| 3a | BG | Step row, only if 3 matched | `discovery_batch` completed (insert, or claimed → completed) | PK / `status=started` |
| 3b | BG | Step row when the breaker is open (no run write) | `discovery_batch` degraded with STEP 3's data (insert, or claimed → degraded) | PK / `status=started` |
| 4 | BG | Save as finished | `status`, `state`, `output`, `retryable=false`, `failure_*=null` | `attempts=n` |
| 4a | BG | Step rows, only if 4 matched | `pipelines` completed | PK / `status=started` |
| 4' | BG | Save as failed (not on lost fence) | `status`, `failure_*`, `retryable` | `attempts=n` |
| 4'a | BG | Step rows, only if 4' matched | the running step failed | PK / `status=started` |
| 5 | E2 | Load a run | — (read, step rows embedded) | `run_id`, `user_id` |
| 6 | E2 | Claim for retry | `status=running`, `attempts=n+1`, `retryable=false` | as A-E2.3 |
| 6a | E2 | Claim step rows | `failed` / `degraded` → `started`, error and output cleared | `status in (failed, degraded)` |
| 7 | BG | Checkpoint / finished / failed (+ step rows) | as 3 / 4 / 4' | `attempts=n+1` |
| 8 | E3 | Load a run (only when not live in memory) | — (read, polled) | `run_id`, `user_id` |

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

The gateway changes in one place, outside the method (R3-C2 Iteration 1):

```
McpToolGateway(parallel, firecrawl, *, ...,
               global_search_semaphore=None,     ◀── NEW, default = today's behavior
               global_firecrawl_semaphore=None,  ◀── NEW
               firecrawl_rate_limiter=None)      ◀── NEW, replaces its own bucket when given
_single_call: rate token → run slot → app-wide slot (if given) → timeout → call_tool
              retries, timeouts, parsing, failure kinds ── unchanged
```

Everything else in R3, including every STEP 3/4 decision, degradation and log line, is untouched.
✅ Scope Boundary

---

## B7 — R3 breaking points and drift register

### B7.1 Product level (what the customer experiences)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| B5 | B-E3.2 | After a hard crash, the row reads `running` for up to 30 min, and retry returns `409 running`. The customer watches a progress screen that will never move. | ⚠ open: report stale `running` as retryable in E3, or let the page offer Retry after a timeout. At one process, "`running` in the row but not in `r3_tasks`" means a crash (R3-C7 Iteration 2), but that breaks with several workers |
| B8 | B5.1 | A run that finishes with some amenities as `pipeline_error` or `resolution_call_failed` is `finished` and can't be retried. Those metrics stay unresolved unless a new R3 run is started (which redoes everything). | ✅ by design (the whole step is the unit; finished is terminal); note for product |
| B9 | B-E1.4 | A start request whose `202` is lost (refresh at that moment) leaves the run going on the server with no `run_id` on the page. | ⚠ open, low impact (the window is milliseconds) |
| B10 | B-E3.0 | Progress is coarse: only `null` → `discovery_batch` → finished. STEP 4 (the longest part) shows no movement. | ✅ accepted (progress isn't in the problem statement) |

### B7.2 Technical level (what the code must handle)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| B11 | R3-C6 | `stale_after = 30 min` must be longer than the longest STEP 4, including waits for the app-wide provider limits (B27). Nothing measures STEP 4 yet. If STEP 4 runs longer, a live run can be reclaimed and both executions spend money. Fencing keeps the data correct, not the cost. | ⚠ open until R3-C9 records live STEP 4 durations, alone and with two runs in parallel |
| B12 | B-BG.2 | The degraded-STEP-3 rule uses `breaker.open` only. STEP 3 items can also end as `none` from per-item provider failures *below* the breaker threshold, and those are saved. A retry then won't rediscover them. | ⚠ open: accepted as "real result" by today's logic, or extend the rule (for example, don't save when any item degraded on `availability`). If extended, the `degraded` step status (R3-C5 Iteration 1) can record it |
| B13 | B-BG.0 | One gateway per run (R3-C2) meant the Firecrawl token bucket and the search and Firecrawl semaphores were per run, so two parallel runs could exceed the account's real limit and get `429`s. | ✅ resolved (R3-C2 Iteration 1): one app-wide limit per provider (Parallel 10 slots; Firecrawl 2 slots + 10/min), behind each run's own limit |
| B14 | Shutdown | A cancelled task's "save as failed" is itself an `await` on the database during shutdown, and the gateway close in the method's `finally` runs before it. If the timeout is hit first, the row stays `running` (→ B5). | ✅ R3-C7 "shutdown": R3's own timeout of 10 s, R3 tasks before the LLM caller and the database close, `r3_run.shutdown_timeout` logs what is left; stale reclaim covers the rest |
| B15 | B-BG.1 | A fresh breaker on resume means an outage that lasts across the retry trips the breaker again, and the one retry is used up. | ✅ accepted (retry is manual; the customer retries when ready) |
| B16 | B-BG.1 | STEP 4's internal `run_id = uuid4().hex` differs from the HTTP `run_id`. Logs carry both (the HTTP one via `run_id_var`). | ✅ decided (R3-C3), note for log readers |
| B17 | B-BG.4 | The cancellation row in the R3-C7 table said "Yes" (retryable) without the limit. | ✅ resolved: R3-C7 states that every "Yes" means `attempts < MAX`, cancellation included |
| B18 | B-E2.3 | The same OR-claim statement as A6, on `r3_runs`. | ⚠ as A6 (manual check on the dev database, R3-C9) |
| B19 | B-BG.2 | The callback is awaited inside the method's `try` with the gateway open, so a slow database write holds the MCP sessions open a little longer. | ✅ negligible (one row update, plus one step row) |
| B25 | B-BG.4 | A refused LLM key is classified `availability` by the provider adapters, and the cause is gone by STEP 5's run-level raise. So the run is saved retryable, and the one retry fails the same way. Only happens when every provider in the chain refuses its key. | ⚠ open, risk accepted (R3-C7 Iteration 1): fixing it changes the shared LLM client's failure classes, which R1 and the breaker read |
| B26 | B-BG.1 | The config-error check expects a `401` / `403` on `McpConnectionError`'s cause chain. The hosted Firecrawl endpoint's real error shape is not confirmed live. If the status isn't there, the run falls back to "retryable". | ⚠ open until the R3-C9 live check with a wrong key |
| B27 | B-BG.1 | When an app-wide pool is full, a run waits for a slot, so STEP 3 / STEP 4 take longer. | ✅ accepted (R3-C2 Iteration 1); feeds B11 |

### B7.3 Architectural level (how the pieces fit)

| ID | Box | What can go wrong | Coverage |
|---|---|---|---|
| B20 | B-E1.3 | Background tasks live in one worker process. With several workers, each worker cancels only its own tasks on shutdown, and a run is owned by whichever worker started it. All state is in `r3_runs`, so this is correct. The app-wide provider limits are per process too, so with several workers each has its own pool. | ✅ no shared in-memory state needed for correctness; ⚠ the provider limits hold only at one process (MVP) |
| B28 | B-E3.0a | The status memory check is per process: a run started by another worker isn't in this process's `r3_tasks`, so status falls back to the row. Correct, only slower. | ✅ accepted (one process at MVP), as R2's A22 |
| B21 | B-E1.4 | Start and retry return `202` with no result. R3 is the only service whose action endpoints don't return the outcome, so the page needs one more pattern (polling). | ✅ chosen (R3-C7); consequence noted |
| B22 | R3-C5 | `output` holds `resolution_results` (marked TEMPORARY). When STEP 6 lands, the output becomes `amenity_records` with a version bump, and in-flight runs then fail as not retryable. | ✅ decided (R3-C5) |
| B23 | R3-C4 | The tuple-key encoding exists only in the R3 store. Any other reader of `r3_runs.state` (debug scripts, a future service) must use the store's loader, not plain JSON. | ✅ by design (one place knows the format) |
| B24 | R3-C5 | Places content (`predefined_records`) is also kept in `r3_runs.state`, with no expiry. | ✅ decided: kept for now; the policy comes in a later phase |

### B7.4 Where to look first

1. **B11:** `stale_after` vs real STEP 4 time, now including waits for the app-wide limits (double spend if wrong).
2. **B12:** which degraded STEP 3 results get saved.
3. **B5:** a crashed run looks alive for up to 30 minutes.
4. **B25 / B26:** refused keys that still read as retryable.

The rest are product choices, or accepted trade-offs already written into the process flow.
