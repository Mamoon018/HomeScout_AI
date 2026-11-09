# R2 & R3 as Independent Services: Problem Context

**Stakeholders:** (1) the apartment seeker, (2) the Deep Search system, meaning the downstream stages and whatever calls R2/R3, (3) the developer who maintains the services.

## User

### Apartment seeker
- **Continuity of progress.** *Want:* a retry continues from where the run stopped. *Friction:* if anything fails partway through, all of it is thrown away. They wait again for discovery, enrichment and web research they already sat through once.
- **Stability of results.** *Want:* places and metric values already found stay the same after a retry. *Friction:* a rerun returns a different place set and different web evidence. What they were comparing changes without them knowing.
- **Privacy of their runs.** *Want:* only they can see, resume or retry their runs. *Friction:* nothing ties an R2/R3 run to the person who started it.

### Deep Search system
- **Independent invocability.** *Want:* R2 and R3 can each be started, checked and retried on their own. *Friction:* today they can only be called in-process, through one shared object. Nothing outside can trigger R3 alone or ask whether R2 finished.
- **Clean ownership of data.** *Want:* each stage holds only its own outputs, plus a defined input it receives from the stage before. *Friction:* one state object mixes R2's outputs (`discovered_places`, `enrichment`, `predefined_records`) with R3's (`website_search_results`, `official_gate_results`, `resolution_results`, `specific_records`, `amenity_records`). Either stage can read or overwrite the other's fields.
- **Known run position.** *Want:* after a failure, the system knows exactly which steps finished. *Friction:* nothing records step completion. After a crash there is no way to tell whether, for example, R3 STEP 4 had finished.
- **Single execution per retry.** *Want:* one failed run is retried once at a time, and no step is started twice for the same attempt. *Friction:* duplicate or simultaneous retry requests would each launch the run. That means paying twice and getting competing results written to the same run.

### Developer
- **Consistency with R1.** *Want:* R2/R3 behave and are structured like R1, so there is one model to learn. *Friction:* R1 has a coordinator, store, routes and run statuses; R2/R3 have none of these. Each new endpoint risks a different pattern.
- **Justified persistence points.** *Want:* every saved point can be defended with a clear rule. *Friction:* with no rule you either save around every call (noise, write cost, schema churn) or miss the step that actually mattered.
- **Proportionate simplicity.** *Want:* resumability that fits a feature with no outside side effects. *Friction:* generic resumability designs (checkpoints on every call, locking systems) cost more to build and maintain than the risk they cover.

## Environment

### (a) Conditions that shape what success looks like
- **Outputs can't be reproduced.** Google Places results, web pages and LLM answers change between calls. Recomputing does not recover a lost result; it produces a new one. Recovery means restoring what was saved.
- **Steps differ in cost.** Some steps are cheap and fully determined by their inputs, for example R3 STEP 1 (plan index) and STEP 2 (work items) are derived from state. Recomputing those is as good as restoring them, so success does not require saving every step.
- **The whole step is the unit of recovery.** R2 runs per-category pipelines and R3 runs per-work-item pipelines, concurrently, inside one step. A step counts as done only when all of its items are done. If it fails partway, the finished items inside it are not kept and the step runs again from its start on retry.

### (b) Conditions that shape how the solution must operate
- **Failures come from both sides.** Runs take minutes over HTTP.
  - *From outside:* client connections drop, requests time out, servers restart, and providers hit rate limits or go down.
  - *From inside:* LLM output fails validation, the circuit breaker opens, code hits a bug, or the stage before hands over bad input.
  - Some of these failures go away on retry and some don't.
- **Retry requests can overlap.** A user or client can send the same retry more than once, at the same time, for one failed run.
  - *How R1 handles it today:* starting a retry is a single conditional update in `mark_retry_started` ([r1_run_store.py:142](../r1_run_store.py)). The update only matches a row that is failed, retryable and at the expected attempts count, and the same write marks it non-retryable.
  - Only one request can match. The losing request gets a conflict ("Another retry of this run already started") and runs nothing ([r1_run_coordinator.py:181](../r1_run_coordinator.py)).
  - R2 and R3 have no equivalent yet.
- **Stages depend on each other in a chain.** R2's input is R1's output (origin, category metric plans). R3's input comes from R1 and R2. Each service's input is another service's saved output.
- **Saved objects must load back exactly.** The state uses dataclasses and tuple keys such as `dict[(int, str), ...]`, which JSON can't store as-is. A saved object has to load back identical, or a resumed run works on different data.
- **The R1 pattern already exists.** FastAPI endpoints, user-scoped Supabase tables, run statuses (paused / finished / failed), retry, and a coordinator plus store. R2/R3 come into a codebase that already has this reference.

*Completeness check:* this explains why the naive versions fail.
- "Just rerun on retry" fails because results can't be reproduced and are costly.
- "Save everything" fails because of cost and complexity.
- "Let every retry request run" fails because of overlapping retries.
- "Trust the input" fails because the stage before can hand over bad input.

## Problem relevance

If R2 and R3 can't be run, tracked and resumed on their own, any failure in a long amenity run throws away expensive results that can't be reproduced. The listings the user is judging would then rest on data that changes with every retry, so the app can't act as a dependable long-running agent.

---

# Refined Problem Statement

The system needs to run Amenity Search (R2) and Specific Metric Resolution (R3) as two independent services. Each one is started, tracked and retried for a specific user on its own. Each holds only the data it produces, plus the input it receives from the stage before it, without changing what either service computes or the objects it produces.

The system must keep the result of every step that is costly or non-reproducible, at the moment the whole step completes, so that a failed run can be retried from the first unfinished step. The retry must not repeat finished steps, and the saved results it builds on must load back unchanged. Steps that are cheap and fully determined by their inputs need not be saved.

The system must ensure that one failed run is retried by only one request at a time, even when the same retry arrives more than once at once. It must tell retryable failures from non-retryable ones, so that a failure that will recur is not retried.

These services must behave like R1 in how they are started, report status, keep their data and handle retries, using the simplest approach that is reliable for a feature with no side effects on other services.

### Traceability check (relevance filter)
| Capability in the statement | Closes which gap |
|---|---|
| Independent start, track and retry per user | Independent invocability, privacy of runs |
| Each service holds only its own data | Clean ownership of data |
| Save costly or non-reproducible steps when the whole step completes | Stability of results; outputs can't be reproduced |
| Resume from the first unfinished step, no repeats | Continuity of progress, known run position |
| Skip saving cheap, determined steps | Justified persistence points, proportionate simplicity |
| One retry at a time per failed run | Single execution per retry; retry requests can overlap |
| Retryable vs non-retryable failures | Failures come from both sides |
| Same behavior as R1 | Consistency with R1 |

Every capability traces back to the relevance gap, so none was cut.

---
---

# Feature Process Flows

Two separate flows follow: **R2 (Amenity Search)** first, then **R3 (Specific Metric Resolution)**. Each reuses the R1 HTTP pattern (`R1_HTTP_Pause_Resume_Process_Flow.md`) wherever it fits, and departs from it only where the problem context above requires.

## Scope Boundary (applies to R2 and R3)

- **Do not change:** the business and decision logic of either service. This covers how places are discovered, enriched and attached (R2), how websites are discovered, how metrics are searched and resolved, and how per-item failures degrade (R3). It also covers the objects each step produces (`CanonicalPlace`, `EnrichmentBundle`, `PredefinedMetricsRecord`, `WebsiteSearchResult`, `OfficialGateRecord`, `DiscoverySearchRecord`, `AmenityResolutionRecord`, …) and how edge cases are handled. Given the same inputs and the same provider responses, each service must produce the same output it does today.
- **May change or add:** only what the Refined Problem Statement asks for:
  - which state object holds which fields (the split);
  - entry points that let a run resume after its last saved step;
  - saving and loading at step boundaries;
  - run tables, run status and retry rules;
  - the HTTP endpoints.
- **Rule for every addition:** each component traces back to a line of the Refined Problem Statement.

## The Persistence Rule (applies to R2 and R3)

A step's output is saved, at the moment the **whole step** completes, only when both of these hold:

1. **It is costly or non-reproducible:** it made paid calls (Google Places/Routes, LLM tokens, web search) or took minutes, or running it again would give a different result.
2. **A failure can still happen before the next save:** at least one external call, LLM call or wait lies between the end of this step and the next write. If the only thing left before the next write is pure in-memory work, the next write (the "finish" write) already covers the step.

Two more rules sit on top of these:

- **Recompute, don't save:** cheap steps that are fully determined by saved data are always recomputed on resume.
- **Never save a degraded step:** a step whose output was degraded by an outage, rather than by real data, is not saved as a checkpoint, so a retry never resumes after it. Saving it would make the outage permanent on retry (see R3-C3). R3 may still keep it as a `degraded` record row in its step table, which no resume or status decision reads (R3-C5 Iteration 1).

## Two Facts the Code Showed (corrections to the Problem Context)

- **R2's input is not only R1's output.** R1's finished output gives `category_metric_plans`. The search **origin** (`GeoPoint`) and **radius** are not part of R1's output, so the R2 start request has to supply them. `radius_km` falls back to `DEFAULT_RADIUS_KM` (2.0).
- **R2 is short and R3 is long.** R2 asks for at most `DISCOVERY_MAX_RESULTS = 10` places per category, then runs one routing re-search per category per mode (walk, drive, cycle) and one transit matrix per 100 places, all concurrently, so it takes seconds. R3 runs LLM turns and web searches for every amenity, so it takes minutes. "Runs take minutes" holds for R3 only. Run length alone would let R2 run inside the request, but R2-C6 Iteration 2 moves R2 to a background task as well, so a refresh can't stop a run (R2-C6 vs R3-C7).

---

# R2. Amenity Search — Feature Process Flow

R2 takes a finished R1 run plus a search origin, and produces one `PredefinedMetricsRecord` per discovered place per category. It needs **8 components**, plus one prerequisite change in R1 (**R2-P1**, the finished output column). R2's three step methods are reused exactly as they are.

## R2 Runtime Flow

1. The customer (or the page, after R1 finishes) sends `POST /api/amenity-search/runs` with `r1_run_id`, `origin` and an optional `radius_km`.
2. The login check verifies the user. The request model checks that `origin` is a finite coordinate and `radius_km` is positive, and rejects bad input with `422` before any row exists.
3. The coordinator reads R1's **finished** output through `R1RunStore.get_finished_output(r1_run_id, user_id)` (new, R2-P1). This is one read of the `r1_runs.output` column. A run that is missing, another user's, not finished, finished before the column existed, or on another `workflow_version` gives `404`. A database error or the 10 s timeout gives `503`. No row exists yet in any of these cases.
4. The coordinator builds `AmenitySearchState(origin, radius_km, category_metric_plans)` and creates the `r2_runs` row with status `running`, `attempts = 0`, `completed_step = null` and this initial state saved. A database error here gives `503`, with no row.
5. The coordinator starts the run as a **background task**, keeps it in `app.state.r2_tasks`, and replies `202 {run_id, status: "running"}` at once (R2-C6 Iteration 2). The page saves `run_id` and polls the status endpoint. Steps 6–10 run in the task.
6. **Step `discovery`** (M1.1, `run_place_discovery`) runs. When it completes, the state is saved as a checkpoint, `completed_step = "discovery"`, and a `completed` `discovery` row is added to `r2_run_steps` (R2-C4 Iteration 1).
7. **Step `enrichment`** (M1.2, `run_accessibility_enrichment`) runs. No save follows, because the next step has no I/O (see the persistence rule).
8. **Step `attachment`** (M1.3, `run_result_attachment`) runs in memory.
9. The **finish write** saves the final state and the output (`category_metric_plans`, `discovered_places`, `predefined_records`) and sets `finished`. A `completed` `enrichment` row is then added to `r2_run_steps`. The page sees it on its next poll.
10. **On any failure,** the run is saved as `failed` with its stage, message and `retryable` flag. The saved state and `completed_step` are left untouched. If `discovery` or `enrichment` was running, that step gets a `failed` row in `r2_run_steps`. The page sees it on its next poll.
11. **Retry:** `POST /api/amenity-search/runs/{run_id}/retry` (no body).
    - The store claims the run in **one conditional update**: it must be `failed` and retryable, or `running` and stale. On success it becomes `running` with `attempts + 1`.
    - A missing run or another user's gives `404`. A finished run, a run that is not retryable or has used its retry, a `running` run that is not stale yet, a version mismatch (saved as failed, not retryable), and a losing request all get `409`.
    - If the step it resumes at has a `failed` row in `r2_run_steps`, that row is claimed (`failed → started`), as in R1.
    - The winner replies `202 {run_id, status: "running", completed_step}`. A background task loads the saved state and resumes at the **first step after `completed_step`**.
12. **Status:** `GET /api/amenity-search/runs/{run_id}` returns `status`, `completed_step`, and `result` or `retryable`. It is read-only. It first checks `app.state.r2_tasks`: a live task of this user's answers `running` with no database read, and another user's gives `404`. Otherwise it reads the row: `404` clears the page's `sessionStorage` (back to SCREEN R1), a version mismatch reads as `failed`, not retryable (no write), and a database error gives `503`. The page polls it every ~2 s while `status` is `running`.
13. **R3** reads the finished output by `run_id` and `user_id` (R2-C4 "Get the finished output").

## What Already Exists and Is Reused As-Is

| Built-in | Where | Used for |
|---|---|---|
| M1.1 / M1.2 / M1.3 step methods | `AmenitySearch.run_place_discovery`, `run_accessibility_enrichment`, `run_result_attachment` | Every step that produces a value |
| R2's typed errors, each with a `stage` | `PlaceDiscoveryError`, `AccessibilityEnrichmentError`, `ResultAttachmentError` in `src/exceptions/deep_search.py` | Failure stage and the retryable split |
| R1 HTTP pattern: coordinator, store, controller, routes, `get_authenticated_user`, `user_id` filter, `RunConflictError` / `RunNotFoundError` / `RunStoreError`, `retryable` in every failed body | `r1_run_coordinator.py`, `r1_run_store.py`, `app/api/...` | The shape every R2 piece copies |
| Async service-role Supabase client, migrations folder | `create_supabase_db_client`, `backend/supabase/migrations/` | The `r2_runs` table |
| `create_amenity_search` factory | `amenity_search.py` | Building a new `AmenitySearch` per run from the shared clients (R2-C2 Iteration 1) |

## R2-P1. R1 Finished Output Column (prerequisite change in R1)

### Goal of Component
R2 reads a finished R1 run's `category_metric_plans` in one read of one column, without loading R1's steps or replaying R1.

### Problem It Aims to Solve
The code showed that `R1RunStore.get_finished_output` does not exist. The current `r1_runs` table (`create_r1_run_steps.sql`) has no `output` column: R1's result lives only in the `r1_run_steps` rows, and R1's own status endpoint rebuilds it by replay. R2 would have to copy that replay to get its input.

**Traces to:** "R2 takes a finished R1 run" and the handoff between independent services.

### Mandatory Sub-Tasks
- **Migration** `<ts>_add_r1_runs_output.sql`, safe to re-run: add `output jsonb` (nullable) to `r1_runs`, and add the CHECK `(status = 'finished') = (output is not null)`.
- **Atomic finish:** R1's move to `finished` writes `status = 'finished'` and `output` (`category_metric_plans`) in **one** UPDATE, still guarded by `expected = 'running'`. No separate write sets one without the other.
- **New store method** `R1RunStore.get_finished_output(run_id, user_id)`: one SELECT of `output` and `workflow_version`, filtered on `run_id`, `user_id` and `status = 'finished'`. It returns the decoded `category_metric_plans`, or `None`.

### Critical Decision Choices
- **Database guard:** the CHECK constraint enforces "a `finished` run always has an output, and no other run has one" in the database, not only in code.
- **Shape version:** the JSON shape of `output` is tied to `workflow_version`. A row with a different version is treated as a version mismatch, as R1 does today. For R2's start this gives `404` (start R1 again).
- **Runs finished before the column:** they have `output = null` and read as `404`. The customer starts R1 again. No backfill (MVP).
- **R1's own status endpoint (E3):** reads `output` for a finished run instead of replaying the steps. It's the same data and a separate change from R2's needs, but it is agreed.
- **Step rows stay:** `r1_run_steps` remain R1's checkpoints for retry. `output` is only the compiled final result and does not replace them.
- **Read behavior:** the read is idempotent and has no retry. A database error or the 10 s client timeout gives `503` ("try again"), kept distinct from `404` ("go back to R1"). It uses the shared async service-role client built in `lifespan`.

## Component Order

```
R2-C1 State split ──► R2-C2 Step plan ─────────────────────────────┐
        └──────────► R2-C3 Serialization ──► R2-C4 Run store ──► R2-C5 Single-execution guard ──► R2-C6 Coordinator ──► R2-C7 HTTP endpoints
                                                                    R2-C8 Verification of C1–C7
```

---

## R2-C1. Separate R2 State and Its Handoff Output

### Goal of Component
R2 has a state object that holds only R2's inputs and outputs. It also has a defined output that R3 receives, so neither service can read or overwrite the other's fields.

### Problem It Aims to Solve
`AmenitySearchState` holds R2's fields (`origin`, `radius_km`, `category_metric_plans`, `discovered_places`, `enrichment`, `predefined_records`) next to R3's (`website_search_results`, `discovery_search_results`, `official_gate_results`, `resolution_results`, `specific_records`, `amenity_records`). Saving R2's state would save R3's empty fields, and a resumed R3 could overwrite R2's data.

**Traces to:** "Each holds only the data it produces, plus the input it receives from the stage before it, without changing … the objects it produces."

### Mandatory Sub-Tasks Independent of Approaches Taken
- Every R2 field keeps its exact name, type and default, so the step methods' bodies don't change.
- R2 code no longer refers to any R3 field.
- The R2 → R3 handoff is defined as `category_metric_plans`, `discovered_places` and `predefined_records`. This is exactly what R3 reads today: STEP 1 reads the plans, STEP 2 the places, STEP 3/4 the records. `enrichment` is not handed over, because R3 never reads it and `predefined_records` already carries the routing views.
- Tests and sample runs that build `AmenitySearchState` with R3 fields are updated to build the R3 state (R3-C1) instead.

### Three Common Approaches
1. **Two state classes with the same field definitions. (Finalized)** `AmenitySearchState` keeps only R2's fields. R3's fields move, unchanged, to a new R3 state (R3-C1). Each service's methods are typed against its own state.
2. **One shared class, with a projection at the store boundary.** `AmenitySearchState` stays as it is. Each store saves and loads only its own service's fields, and the other fields stay at their defaults.
3. **R3 state wraps a frozen R2 output object.** R3's state holds `r2_output: AmenitySearchOutput` (read-only) plus its own fields. R3 code reads `state.r2_output.predefined_records`.

### Critical Factors (from our context)
- **Clean ownership (Want):** a service must be *unable* to touch another's fields, not just avoid saving them.
- **Zero change to decision logic (Scope):** method bodies must stay as they are.
- **Consistency with R1 (Want):** R1 has one state class per service.

### Reasoning
- **Approach 2** keeps both services able to write each other's fields in memory. A resumed R3 holding a full `AmenitySearchState` could still change `discovered_places`. It hides the problem instead of removing it, so it fails *clean ownership*.
- **Approach 3** makes ownership strict, but every R3 read of `state.predefined_records` and `state.discovered_places` changes to `state.r2_output.…`. That edits R3's method bodies across STEPs 2–4, which conflicts with *zero change*.
- **Approach 1** removes the shared object, and R3 still reads `state.category_metric_plans`, `state.discovered_places` and `state.predefined_records` under the same names. Only type annotations change. The handoff fields are copied into R3's state once, at R3 start. It is the only option that meets all three factors.

### Critical Decision Choices
- **General — where the new class lives:** in `feature_schemas/schemas.py`, next to `AmenitySearchState`, as the existing schemas are.
- **Context-specific — do handoff fields become frozen in R3?** No. Freezing them would change how R3's objects behave. Ownership is enforced by R3's store never writing R2's table (R3-C5), and by R2's output being read-only from R3's side.
- **Context-specific — `specific_records` and `amenity_records`:** both are R3 outputs (Mechanism 3 / STEP 6, not built yet), so they move to R3's state, with the same defaults.

---

## R2-C2. R2 Step Plan and Persistence Points

### Goal of Component
R2 runs as a named, ordered list of steps, with a known save point after each costly step. It can start from any step given the saved state.

### Problem It Aims to Solve
Nothing defines R2's steps as resumable units or which of them are saved, so a retry has no way to skip discovery that already finished.

**Traces to:** "keep the result of every step that is costly or non-reproducible, at the moment the whole step completes", "retried from the first unfinished step", "Steps that are cheap … need not be saved."

### Mandatory Sub-Tasks Independent of Approaches Taken
- The step table below, applying the persistence rule:

  | Step | Method | Costly? | Non-reproducible? | Save after? |
  |---|---|---|---|---|
  | `discovery` | `run_place_discovery` | Yes: one paid `searchNearby` per category | Yes: results and ranking change | **Yes**, a checkpoint with `completed_step = "discovery"` |
  | `enrichment` | `run_accessibility_enrichment` | Yes: a routing re-search per mode, plus a Routes matrix | Yes: travel times change | **No separate save.** The next step has no I/O, so the finish write covers it |
  | `attachment` | `run_result_attachment` | No: pure, in-memory | No | Covered by the **finish write** (state + output) |

- **Resume rule:** `completed_step = null` → start at `discovery`. `completed_step = "discovery"` → start at `enrichment`.
- The order and the methods called are exactly the order a one-call R2 run uses today.

### Three Common Approaches
1. **The coordinator calls the three existing public step methods in order, saving between them. (Finalized)** A small ordered list `[("discovery", run_place_discovery, save=True), ("enrichment", …, save=False), ("attachment", …, save=False)]` lives in the coordinator. `AmenitySearch` is unchanged.
2. **One new entry on `AmenitySearch`:** `run(state, *, resume_after, on_step_completed)`. It runs the steps itself and awaits a save callback after each saved step.
3. **State-inferred resume inside the service.** Each step is skipped when its output field is already filled (`discovered_places` non-empty → skip discovery).

### Critical Factors (from our context)
- **Zero change to the service:** R2's three steps are *already* separate public methods.
- **No run-scoped resources:** R2 holds no session or breaker that has to live across steps. The Places/Routes clients are long-lived and shared. (Iteration 1 adds a per-run `AmenitySearch` that holds only its own semaphore.)
- **Exact resume position:** a step's output being empty is a valid result (a category can have zero places).

### Reasoning
- **Approach 3** breaks on valid empty outputs. A discovery that found nothing would be repeated on every resume, so it fails *exact resume position*.
- **Approach 2** is right when steps share run-scoped resources (as in R3), but R2 has none. Adding the entry would mean new service code with nothing to gain.
- **Approach 1** needs no change to `AmenitySearch` at all, keeps knowledge of persistence out of the service, and the coordinator can test the plan directly.

### Critical Decision Choices
- **General — where the step list lives:** in the R2 coordinator, as a module-level ordered tuple, so the resume rule and the step order can't drift apart.
- **Context-specific — enrichment checkpoint:** left out on purpose, by rule 2 of the persistence rule. **Risk accepted:** a hard crash in the moment between enrichment ending and the finish write would repeat enrichment on retry.
- **Context-specific — the empty-place shortcut:** `run_accessibility_enrichment` returns early when no place has a location. This is unchanged, and the plan treats it as a completed step.

### Iteration 1 — Places Concurrency: Per-Run Limit Plus One Global Cap (step `discovery`)

**What changed.** The original design built one `AmenitySearch` at startup and shared it across every run. Its one Places semaphore of 3 then capped **all customers together**, so one customer's run queued behind every other customer's. This iteration picks a middle ground: a limit per run plus one global cap.

**Design**

- **App level (`lifespan`):** build the Places and Routes clients once, as today, and also **one global Places semaphore of 15**. Store all three on `app.state` and pass them to the R2 coordinator.
- **Instance level (per run):** for each run, the coordinator builds a **new `AmenitySearch`** from the shared clients and the shared global semaphore. The constructor still creates its own semaphore of 3.
- **Slot order:** each Places call takes its **run slot first, then a global slot**, and releases both when it returns.
- **Result:** each customer gets up to 3 Places calls at a time, and the whole process never has more than 15 in flight.

**Mandatory sub-tasks**

- `AmenitySearch.__init__` gets two optional keyword arguments, with defaults that keep today's behavior for standalone use and the existing suites:
  - `global_places_semaphore: asyncio.Semaphore | None = None`: when it's set, every Places call (`execute_discovery` and the routing re-search) takes it inside the run semaphore.
  - `owns_clients: bool = True`: when it's `False`, `aclose()` doesn't close the shared Places/Routes clients. The per-run instance is built with `owns_clients=False` and `owns_caller=False`.
- `lifespan` closes the shared Places and Routes clients on shutdown, after it has cancelled and awaited the R2 tasks (R2-C6 Iteration 2). No run closes them.
- R2-C7's startup builds the shared clients and the global semaphore, not a single `AmenitySearch`.

**Why the slot order matters.** A run waiting on its own limit of 3 never holds a global slot, so a busy run can't hold global slots it isn't using. Five runs at full speed fill the 15. A sixth waits only for the global cap.

**Critical Decision Choices**

- **General — the global cap's size (15):** five customers at full per-run speed. This stays well below Places' per-minute quota at MVP traffic.
- **Context-specific — what the global cap covers:** Places calls only (discovery and the routing re-search, which share the Places semaphore). The Routes transit matrix keeps only its per-run limit of 3. Its call count is ⌈P/100⌉ per run, so it's too small to need a global cap at MVP.
- **Context-specific — one process:** the cap is per process. With several workers, the real cap is 15 × workers. Accepted for MVP (one process). Revisit with more workers or with Places `429`s.
- **Context-specific — effect on R2-C2's "zero change to the service":** the step methods and their logic are unchanged. Only the constructor (two optional arguments) and `aclose` are touched. Run-scoped state is still none apart from the run semaphore, so Approach 1 (the coordinator's step list) still holds.
- **Risk accepted:** when the global cap is full, the wait for a slot lengthens the run (traceflow A19). Since R2-C6 Iteration 2 the run is a background task, so the wait no longer holds a request open.

---

## R2-C3. R2 State Serialization

### Goal of Component
A saved R2 state (initial, after discovery, finished) turns into JSON and back with nothing lost.

### Problem It Aims to Solve
The state uses `dict[int, dict[str, CanonicalPlace]]` (int keys become strings in JSON), dataclasses, and `CanonicalPlace.place`, which is a raw `Place.to_dict` dict. A resumed run must see exactly the data the first attempt saw.

**Traces to:** "the saved results it builds on must load back unchanged."

### Mandatory Sub-Tasks Independent of Approaches Taken
- Round-trip tests for the initial, after-discovery and finished states, comparing JSON dumps.
- A version number in every saved state, `R2_STATE_SCHEMA_VERSION`. A mismatch raises `StateVersionMismatchError`, which marks the run `failed` and not retryable, as in R1.
- A round trip for the output (handoff) object as well.

### Three Common Approaches
1. **Pydantic `TypeAdapter` over the existing classes, inside a version envelope. (Finalized)** The same method R1 uses (`dump_state` / `load_state`).
2. **Hand-written `to_dict` / `from_dict` per class.**
3. **`pickle` into a `bytea` column.**

### Critical Factors (from our context)
- **Exact round trip without touching the classes (Scope).**
- **Consistency with R1 (Want).**
- **Readable stored data** for debugging, since a failed run is inspected in Supabase.

### Reasoning
- **Approach 3** round-trips exactly, but it is unreadable and breaks on any class move. It also runs code on load, which is unsafe for a database value.
- **Approach 2** means new code for about a dozen classes, which must be kept in step with every schema change.
- **Approach 1** already works for R1. R2's state has **no tuple keys** (`int` and `str` keys only), and Pydantic restores `int` keys. It is the smallest choice and the most consistent with R1.

### Critical Decision Choices
- **General — version mismatch after a deploy:** reject (failed, not retryable), as in R1, since runs are short-lived.
- **Context-specific — `CanonicalPlace.place` is an untyped `dict`:** it is saved as-is. The round-trip test must include real `Place.to_dict` output (enums, nested `display_name`, `location`, `reviews`) to prove it is JSON-safe.

---

## R2-C4. R2 Run Store (`r2_runs`)

### Goal of Component
Each R2 run is one database row tied to its user and its R1 run. It holds the status, the single R2 state, the last completed step, the output and the failure details. Other code can create, checkpoint, finish, fail, claim, load and read the finished output.

### Problem It Aims to Solve
R2 has no table and no write path.

**Traces to:** "started, tracked and retried for a specific user on its own", "keep the result of every step … at the moment the whole step completes", "behave like R1 in how they … keep their data".

### Mandatory Sub-Tasks Independent of Approaches Taken
- A migration `backend/supabase/migrations/<ts>_create_r2_runs.sql` that is safe to re-run (`create table if not exists`, an index on `user_id`, RLS on with no policies, and the `updated_at` trigger), copied from `create_r1_runs.sql`. Columns:
  - `run_id`, `user_id`;
  - `r1_run_id`, referencing `r1_runs` (`on delete cascade`);
  - `status`: `running` | `finished` | `failed`;
  - `state` (jsonb, versioned);
  - `completed_step` (text, null until the first checkpoint);
  - `output` (jsonb);
  - `failure_stage`, `failure_message`, `retryable`, `attempts`, `created_at`, `updated_at`;
  - the check `(status = 'finished') = (output is not null)`.
- Every read and write filters on `run_id` **and** the verified `user_id`. Every write is one single-row update, so status and data change together.
- **"Save as failed" never touches `state` or `completed_step`.** A retry resumes from the last good checkpoint.
- A store class `R2RunStore` in `r2_run_store.py`, using the same async service-role client.

### Store Operations
| Operation | What it does |
|---|---|
| **Create a run** | Inserts the row with `running`, the initial state, `attempts = 0` and `completed_step = null`. |
| **Save a checkpoint** | Writes `state` and `completed_step` **if** the row is `running` at the caller's `attempts` (the fencing filter, R2-C5). Returns false otherwise. |
| **Save as finished** | Writes the final state and output and sets `finished`, under the same fencing filter. |
| **Save as failed** | Sets `failed`, the stage, the message and `retryable`, under the same fencing filter. It leaves `state` and `completed_step` untouched. |
| **Claim for retry** | The conditional update from R2-C5. |
| **Load a run** | Reads the row, including `state` (via R2-C3), `completed_step`, `attempts`, `retryable` and `updated_at`. |
| **Get the finished output** | R2's output for R3, or nothing unless the status is `finished`. |
| **Step rows (Iteration 1)** | `insert_step`, `save_step_failed`, `claim_failed_step`, `complete_claimed_step` on `r2_run_steps`, as in R1. `load_run` also returns the step rows. |

### Three Common Approaches
1. **One row per run: the whole state as one versioned jsonb, plus a `completed_step` column. (Finalized)** Each checkpoint rewrites `state`.
2. **A run row plus a step-output table** `r2_run_steps(run_id, step, output jsonb, primary key (run_id, step))`. Each step's own output is inserted once, and a resume rebuilds the state from the rows. This is the durable-workflow "operation outputs" pattern. (Iteration 1 adds such a table as a per-step record only; resume still reads `state` and `completed_step`.)
3. **One row with a column per step output** (`discovered_places jsonb`, `predefined_records jsonb`, …) in place of one `state` blob.

### Critical Factors (from our context)
- **Status and data change together:** one update, with no partial checkpoint.
- **Consistency with R1:** R1 uses one row per run, one `state` blob, a single-row update and a separate `output`.
- **Few save points:** R2 has one checkpoint and one finish write, so rewriting the whole state costs nothing that matters.
- **Proportionate simplicity.**

### Reasoning
- **Approach 2** is the right fit for long workflows with many steps, or steps with external side effects that must never run twice, where a primary key on `(run_id, step)` deduplicates. R2 has one checkpoint and no external side effects. The second table adds a join, a rebuild path, and a second write that has to be atomic with the status change.
- **Approach 3** ties the table schema to the state's fields, so every field change becomes a migration, and the version envelope stops protecting the whole state.
- **Approach 1** is R1's layout plus one column. With two writes per run, the size of a rewrite doesn't matter.

### Critical Decision Choices
- **General — the separate `output` column:** kept, as in R1, so R3 reads a small, stable contract instead of the full state.
- **Context-specific — Google Places content is stored.** The saved state and output hold Places fields: name, address, location, reviews and others. Google Maps Platform terms allow lat/lng to be cached for up to **30 consecutive days**, and place IDs are covered by the Places API Policies. Other content has narrower rules. **Decision:** the data is kept in the database with no expiry for now. A retention policy (for example the 30-day limit) will be decided in a later phase and is not built in this feature.
- **Context-specific — deleting an R1 run:** it cascades to its R2 runs, so an output can never point at a missing input.

### Iteration 1 — A Step Table `r2_run_steps`, Filled as R1 Fills `r1_run_steps`

**What changed.** R2 gets a second table, `r2_run_steps`, with one row per non-reproducible step, written the same way R1 writes `r1_run_steps`. Every other R2 decision stays as it is: `r2_runs` keeps `state`, `completed_step`, `output`, the failure columns, `retryable`, `attempts` and fencing, and **`r2_runs` alone decides where a retry resumes**. The step table is a per-step record next to it, not a second source of truth.

**The table** (migration `<ts>_create_r2_run_steps.sql`, safe to re-run, copied from `create_r1_run_steps.sql`):

- `run_id` (references `r2_runs`, `on delete cascade`), `step_id`, `status`, `output`, `error_type`, `error_message`, `retryable`, `created_at`;
- primary key `(run_id, step_id)`;
- `step_id` in (`discovery`, `enrichment`): the two non-reproducible steps. `attachment` is pure, so it has no row, as R1 has no row for its recomputed steps;
- `status` in (`started`, `completed`, `failed`);
- the checks `(status = 'completed') = (output is not null)` and `(status = 'failed') = (error_type is not null and retryable is not null)`;
- `output` in R1's envelope `{"schema_version", "data"}`: `discovered_places` for `discovery`, `enrichment` for `enrichment`;
- RLS on with no policies, and a trigger that rejects any change to a `completed` row.

**How it is filled (R1's four operations)**

| R1 operation | R2 use |
|---|---|
| `insert_step` (new `completed` row; a duplicate key means another execution) | `discovery` right after the checkpoint write succeeds. `enrichment` right after the finish write succeeds. |
| `save_step_failed` (new `failed` row, or `started → failed` on a claimed step) | When `discovery` or `enrichment` fails: the step that was running gets a `failed` row with `error_type`, `error_message` and the same `retryable` as the run. |
| `claim_failed_step` (`failed → started`, error cleared) | After the run claim (R2-C5) wins, if the step R2 resumes at has a `failed` row, it is claimed. |
| `complete_claimed_step` (`started → completed` with the output) | The claimed step's row is completed at its write point (checkpoint for `discovery`, finish for `enrichment`). |

**Write order.** The `r2_runs` write goes first, fenced as today. The step row follows only when that write matched. So:

- a lost fence writes no step row;
- a duplicate step row or a claimed row that moved is logged (`r2_run.step_conflict`) and stops the execution, as R1 does;
- a store failure on the step row is logged only. The run row is already right, so the run carries on.

**Why `enrichment`'s row waits for the finish write.** A completed row can never change. If `enrichment` were recorded the moment it completed and `attachment` then failed, a retry would rerun `enrichment` (the resume point is still `discovery`) and collide with its own completed row.

**Mandatory sub-tasks**

- `R2RunStore` adds `insert_step`, `save_step_failed`, `claim_failed_step` and `complete_claimed_step`, with R1's signatures and the same `dump_step_output` / `load_step_output` envelope.
- `load_run` reads the run with its step rows embedded, as R1's `load_run` does, and fails loudly if the embed is missing.
- The coordinator calls them at the points in the table above, with no change to the step plan, the resume rule or the retryable split.
- R2-C8 adds the step-table tests (see R2-C8).

**Critical Decision Choices**

- **Context-specific — the run row stays the truth:** resume uses `completed_step`, and status uses `r2_runs.status`. If a crash lands between the run write and the step write, the step row is missing. That gap is in the record only, and no decision reads the step table.
- **Context-specific — the same data is stored twice:** `discovered_places` is in `state` and in the `discovery` row, and `enrichment` is in the final `state` and in the `enrichment` row. That is accepted as a cost. The Google Places content rule (above, traceflow A16) covers both tables: kept with no expiry for now.
- **Context-specific — a crashed run has no `failed` row:** a stale `running` run that is reclaimed has nothing to claim, so the resumed step is inserted as a new row, as on a first run.
- **Context-specific — atomicity:** as in R1, the run write and the step write are separate statements (PostgREST has no transaction across them). The write order above keeps the run row correct whichever one fails.

---

## R2-C5. Single-Execution Guard (Claim, Stale Run, Fencing)

### Goal of Component
Only one execution of a run is ever active, even with duplicate or simultaneous retry requests and after a server restart mid-run. A crashed run can still be retried.

### Problem It Aims to Solve
- **R1's guard isn't enough here.** R1 creates its row as "failed, not retryable" while the run is working, so a crash leaves a run that can't be retried. That is fine for R1, whose retry only reruns from saved answers. R2 has to survive restarts ("servers restart", Environment b).
- **The opposite default breaks the other want.** If a working run were marked retryable, a retry arriving mid-run would start a second copy, which breaks "ongoing step does not get initiated again".

**Traces to:** "retried by only one request at a time, even when the same retry arrives more than once at once", "retry must not repeat finished steps".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **One conditional update decides the winner**, as in R1's `mark_retry_started`: only one request can match. The loser gets `409` ("Another retry of this run already started") and runs nothing.
- **Fencing on every write after the claim:** checkpoint, finish and fail all filter on `attempts = <this execution's attempts>`. An older execution that wakes up late can't overwrite the newer one's data. Its write matches nothing, and it stops.
- **Retry limit:** `MAX_RETRY_ATTEMPTS = 1`, as in R1. Reclaiming a stale run counts as the retry.
- **Step-row claim (R2-C4 Iteration 1):** after the run claim wins, a `failed` row for the step the retry resumes at moves to `started`, as R1's `claim_failed_step`. If that row has moved, the run is set `failed`, not retryable, and the retry returns `409` ("start again"), as R1's `step_conflict`. A stale-reclaimed crash has no `failed` row, so there is nothing to claim.

### Three Common Approaches
1. **R1's guard as-is.** Rows start as "failed, not retryable". Retry is allowed only for `failed` + retryable, via a conditional update. No crash recovery.
2. **A `running` status that becomes stale after a fixed time since the last write, plus `attempts` fencing. (Finalized)** Claim succeeds when `(status = 'failed' AND retryable AND attempts = n) OR (status = 'running' AND updated_at < now() - stale_after AND attempts = n)`, and the same update sets `running` and `attempts = n + 1`. Every checkpoint moves `updated_at`, so it acts as a heartbeat at step boundaries.
3. **A heartbeat lease.** `lease_expires_at` is renewed every N seconds by a background task while the run works. Claim succeeds when the lease has expired.

### Critical Factors (from our context)
- **Crash recovery is required:** "servers restart".
- **No double execution:** a retry must never overlap a run that is alive.
- **Proportionate simplicity:** "reliable but simple".
- **Recovery delay is acceptable:** the product runs as a long-lived agent, so waiting minutes after a rare hard crash is fine.

### Reasoning
- **Approach 1** fails *crash recovery*: a crash leaves the run unretryable, so all saved work is lost.
- **Approach 3** recovers fastest, but adds a timer task per run, a lease column, and renewal failure handling. That is more moving parts than the risk justifies here.
- **Approach 2** recovers from crashes, still stops overlapping retries (a live run is never stale), and needs one timestamp comparison in the update R1 already has. Fencing covers the rare case where a run is slower than `stale_after`. A clean shutdown doesn't even wait: `lifespan` cancels the run's task, and the task saves the run as failed with `retryable = attempts < MAX` (R2-C6 Iteration 2).

### Critical Decision Choices
- **General — whose clock:** `updated_at` is set by the database trigger. The stale cutoff is computed in the backend and passed as a filter. A small clock skew only shifts the wait slightly. The value must be much longer than the skew.
- **Context-specific — `stale_after` for R2:** **10 minutes**, as a setting. R2's longest step takes seconds, so this is very generous.
- **Context-specific — what a lost fence does:** the old execution logs `r2_run.superseded`, makes no further writes, and stops. Since R2-C6 Iteration 2 it runs in a background task with no request attached, so nothing is returned; the page sees the newer execution's result through the status endpoint.

---

## R2-C6. R2 Run Coordinator

### Goal of Component
One service runs R2's step plan around the store. Start: check inputs → load R1 output → create the row → start a background task and reply `202` → (in the task) run the steps → checkpoint → finish. Retry: load → pre-check → claim → start a background task and reply `202` → (in the task) resume after `completed_step` → finish. Any R2 error saves the run as failed with its stage and `retryable` flag (Iteration 2).

### Problem It Aims to Solve
C2 knows the steps and C4/C5 know the database, but nothing applies the status, retry and fencing rules. In the HTTP layer they couldn't be tested without a server.

**Traces to:** "started, tracked and retried … on its own", "retried from the first unfinished step", "tell retryable failures from non-retryable ones".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **The run ID** is created once at start and set on `run_id_var`, so every log line carries it, as in R1.
- **The retryable split:**

  | Error | Retryable | Why |
  |---|---|---|
  | `PlaceDiscoveryCallError`, `RoutingRetrievalError`, `TransitRetrievalError` | Yes, while `attempts < MAX_RETRY_ATTEMPTS`, **unless the config-error check finds a config cause** (Iteration 1) | Provider failure; a second call may succeed |
  | The same three, with Google's original error `InvalidArgument`, `FailedPrecondition` or `PermissionDenied` (Iteration 1) | No | Our setup or request is wrong (bad key, API off, request rejected); it fails again |
  | `PlaceDiscoveryRequestError` | No | Bad input (empty taxonomy node, no `places.*` targets); it fails again |
  | `ResultAssemblyError` | No | The plans and the places don't match; it fails again |
  | `StateVersionMismatchError` | No | Start again (R2-C3) |
  | Any other exception | No, stage `unexpected` | A bug |
  | Cancellation (shutdown; since Iteration 2 a client leaving no longer cancels the run) | Yes, while `attempts < MAX_RETRY_ATTEMPTS` (a cancelled retry is not retryable) | Best-effort save as failed, then re-raise |

- `R2_STAGE_ERRORS` / `R2_PROVIDER_ERRORS` tuples next to R1's, with `502` vs `503` mapped as R1 does. Since Iteration 2 these codes are not sent to the page; the failure is saved on the row and read through the status endpoint.
- An `R2RunFailedError` that carries `run_id`, `stage`, `retryable` and `provider_unavailable`, mirroring `R1RunFailedError`.
- "Save as failed quietly": if the store is down too, log it, as in R1. The row stays `running` and can be reclaimed after `stale_after` (R2-C5). Since Iteration 2 there is no reply to return the error in.

### Three Common Approaches
1. **Run inside the request.** As R1 does: the start or retry request waits until R2 finishes or fails and gets the result in the response. (Chosen first; replaced by approach 2 in Iteration 2.)
2. **`202 Accepted` + in-process background task + status polling. (Finalized for R2, Iteration 2)**
3. **An external job queue and worker** (for example arq with Redis): the request queues a job and a worker process runs it.

### Critical Factors (from our context)
- **Run length:** R2 takes seconds, not minutes (see the corrections above).
- **Consistency:** R1 runs inside the request; R3 runs in a background task with polling (R3-C7).
- **Refresh recovery (Iteration 2):** a refresh must not lose the `run_id`, stop the run, or leave the page waiting with nothing to poll.
- **Proportionate simplicity:** no new infrastructure exists (no Redis or worker).
- **Crash recovery** is already handled by R2-C5, whichever model is used.

### Reasoning
- **Approach 3** survives process loss best and scales out, but it brings new infrastructure and a deployment unit for a step that takes seconds.
- **Approach 2** is right for runs that outlast proxy and browser timeouts (R3-C7). The first reasoning held that for R2 it would only add polling for no benefit. Iteration 2 reverses that, for refresh recovery (below).
- **Approach 1** fits a seconds-long run and matches R1. It was the first choice, on the view that it loses nothing when the connection drops. Iteration 2 shows two gaps it leaves: a refresh before the reply leaves the page with no `run_id` (A2), and after a refresh the page waits on a reply that no longer exists.
- **Approach 2 (Iteration 2)** reuses R3's model, which is already in the design (R3-C7). The request only checks inputs and creates the row, so the page gets `run_id` in milliseconds, and the run never depends on the connection.

### Critical Decision Choices
- **General — what the response carries:** `result` = `predefined_records` (what the page shows), plus `run_id`, `status` and `completed_step`. Since Iteration 2, `result` comes from the status endpoint; start and retry reply `202` with `run_id` and `status: running`.
- **Context-specific — the R1 run must be the same user's and `finished`:** `get_finished_output` (R2-P1) filters on both, and returns nothing otherwise. Every such case gives `404`, with no second read. There is no `409` path: the page only offers R2 after R1 is finished, so an unfinished R1 is not designed for, and the `finished` filter still stops it.
- **Context-specific — whether a client disconnect cancels the handler:** resolved by Iteration 2. Starlette 1.6 doesn't cancel the handler when the client leaves, and the run no longer depends on the handler anyway: it is a background task.
- **Context-specific — two R2 runs for the same R1 run:** allowed. Each is its own run, since starting twice is a deliberate customer action and not a retry. Not deduplicated (not in the problem statement).

### Iteration 1 — Config Errors Are Not Retryable (steps `discovery` and `enrichment`)

**The problem.** R2 wraps every Google error in its own error type. By the time the coordinator sees it, a "bad key" error and a "Google is down" error both look like `RoutingRetrievalError` (or `PlaceDiscoveryCallError` / `TransitRetrievalError`), so both are marked retryable. The customer gets a Retry button that can't work, uses up the one retry, and then hits "Start again", which fails the same way.

**What `__cause__` is.** When Python wraps one error in another (`raise X from Y`), it keeps the original in `X.__cause__`. In R2 this forms a chain:

```
RoutingRetrievalError          ← what the coordinator sees
  └─ __cause__: PlacesClientError
       └─ __cause__: PermissionDenied   ← the real reason, from Google
```

The same chain holds for discovery (`PlaceDiscoveryCallError` → `PlacesClientError` → Google) and transit (`TransitRetrievalError` → `RoutesClientError` → Google).

**The fix.** One small helper in the coordinator follows that chain down to Google's original error:

- **It finds `InvalidArgument`, `FailedPrecondition` or `PermissionDenied`:** our setup or request is wrong, and retrying won't help. Save the run with `retryable = false` and log `r2_run.config_error` (ERROR, with the step and the Google error class) so we notice.
- **Anything else:** keep today's rule (`retryable = true` while `attempts < MAX_RETRY_ATTEMPTS`).

**Mandatory sub-tasks**

- The helper `_is_config_error(exc) -> bool` walks `__cause__` (with a depth limit, so a cycle can't loop) and checks each link against the three `google.api_core.exceptions` types.
- The coordinator's failure handling calls it before applying the retryable table, for all three provider error types.
- The failure keeps its stage ("other R2 error", `502` before Iteration 2). Only `retryable` changes.
- R2-C8 adds one test per step: an injected `PermissionDenied` under each of the three R2 errors gives `retryable: false` and one `r2_run.config_error` log. An injected `ServiceUnavailable` still gives `retryable: true`.

**Why this way**

- **One helper covers both steps:** discovery and enrichment errors are wrapped the same way.
- **R2's code stays unchanged:** only the coordinator's decision changes, so the "reused as-is" rule for the step methods holds.
- **Result:** the customer never sees a Retry button that can't work, and we see the config problem in the logs.

**Critical Decision Choices**

- **Context-specific — the Routes API case:** Places and Routes are enabled separately. If Routes is off, or the key isn't allowed to call it, discovery passes and is saved, and then every enrichment fails in transit. Without this check, that run would be retryable and fail again. With it, the run ends as not retryable at once.
- **Context-specific — `ResourceExhausted` (rate limit) stays retryable:** a per-minute quota recovers by the time the customer clicks Retry.
- **Risk accepted:** the check depends on R2 and the clients keeping `raise … from exc`. If a future change drops the cause, the run falls back to today's rule (retryable). The R2-C8 tests catch that.

### Iteration 2 — Run in a Background Task + Polling (start and retry)

**The problem.** With approach 1, the run lives inside the request, and that leaves two gaps:

- **A2, no `run_id` to recover:** the page gets `run_id` only with the final reply. A refresh during the run leaves it nothing to call E3 with, so the customer is sent back to SCREEN R1 while the run may still finish on the server.
- **The waiting reply:** after a refresh the page shows "waiting" from E3, but the reply it was waiting for is gone, and nothing tells it to look again.

**The new flow**

1. **Start (E1):** login check → input check → read R1's finished output → create the row. Then start the run as a task, reply `202 {run_id, status: "running"}`.
2. **Retry (E2):** load → pre-check → claim. Then start the resumed run as a task, reply `202 {run_id, status: "running", completed_step}`.
3. **The task** runs the step plan as before (discovery → checkpoint → enrichment → attachment → finish write), and saves `finished` or `failed` to the row. Nothing is sent to the page.
4. **The page** saves `run_id` as soon as the `202` arrives, then polls E3 every ~2 s while `status` is `running`, and shows SCREEN R2, F or S from the row.

**Mandatory sub-tasks**

- **The task set:** `app.state.r2_tasks`, keyed by `run_id`, holding `(task, user_id)`. The entry is added when the task starts and removed by a done callback. It keeps the task referenced, so it can't be garbage-collected mid-run (as R3-C7).
- **Shutdown rule:** `lifespan` cancels every task in `r2_tasks` and awaits them, with a short timeout, **before** it closes the shared Places and Routes clients. Each task saves its run as failed with `retryable = attempts < MAX` on `CancelledError` (the cancellation row above), the same as R3.
- **In-memory check in E3:** before the database read, E3 looks up `run_id` in `r2_tasks`:
  - found, same `user_id` → `200 {run_id, status: "running"}`, no database read;
  - found, another user's → `404`, as the database read would give;
  - not found → the database read as before (finished, failed, a crashed run, or a run owned by another process).
- **Errors after the `202`:** the run's `502`/`503`/`500` codes no longer reach the page. The failure is saved on the row (`failure_stage`, `retryable`) and E3 reports it. A lost fence (a newer execution owns the row) is logged only.
- **R2-C8** adds a background lifecycle test and an E3 memory-check test (see R2-C8).

**Why this way**

- **R3's model, reused:** the task set, the shutdown rule and polling are already decided for R3 (R3-C7, R3-C8). R2 copies them, so there is one execution model for both services.
- **A refresh never stops a run:** the run doesn't depend on the request, so A4 (does a disconnect cancel the handler?) is no longer a risk.
- **The `run_id` arrives in milliseconds:** A2's window shrinks from the whole run to the time it takes to create the row.
- **Polling is cheap:** a run of ~30 s polled every ~2 s is about 15 requests. The memory check answers most of them with no database read.

**Critical Decision Choices**

- **Context-specific — the memory check is per process:** a run started by another worker isn't in this process's set, so E3 falls back to the database. That is correct, only slower. At MVP there is one process.
- **Context-specific — the order of save and removal:** the task saves its final status before the done callback removes it, so a poll never sees "not in memory" while the row still says `running` for a live run.
- **Context-specific — the memory reply has no `completed_step`:** it is only read from the row. The page shows plain "waiting" for R2, which is short enough.
- **Still open — A5:** a run that crashed (process killed) is gone from memory and reads as `running` from the row until it is stale (10 min). The memory check can't tell this apart in another process, so A5 stays as it is.

---

## R2-C7. R2 HTTP Endpoints

### Goal of Component
The page reaches R2-C6 over HTTPS with start, retry and status, behind the login check, with R1's status codes and body shapes.

### Problem It Aims to Solve
No R2 routes exist, and app startup doesn't build R2 or its store.

**Traces to:** "started, tracked and retried for a specific user", "behave like R1 in how they are started, report status … and handle retries".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **Startup:** at app startup (`lifespan`), build the shared Places and Routes clients, the global Places semaphore of 15 (R2-C2 Iteration 1), `R2RunStore` and the coordinator once. The coordinator builds a new `AmenitySearch` per run from these, with the shared LLM caller injected. Also create the task set `app.state.r2_tasks` (R2-C6 Iteration 2). On shutdown, cancel and await the tasks in `r2_tasks` (short timeout) first, then close the Places/Routes clients. Set `app.state.r2_run_coordinator = None` when the service-role key is missing (giving `503`, as R1 does).
- **Layers:** a dependency `get_r2_run_coordinator`, a routes file of declarations only, and a controllers file that maps typed errors to codes, copying R1's split.
- **Models:** `StartAmenitySearchRequest { r1_run_id: UUID, origin: {latitude, longitude}, radius_km?: float > 0 }`, plus a response that adds `completed_step`.
- **Bodies:** every failed body carries `retryable`.
- **Wiring:** register the router and add a Swagger tag.

### Three Common Approaches
1. **Separate action endpoints under `/api/amenity-search/runs`, mirroring R1. (Finalized)**

   | Purpose | Method and path | Success | Errors |
   |---|---|---|---|
   | Start | `POST /api/amenity-search/runs` | `202` + `run_id`, `status: running` | `422` bad origin/radius; `404` R1 run not found or not finished; `503` store down |
   | Retry | `POST /api/amenity-search/runs/{run_id}/retry` (no body) | `202` + `run_id`, `status: running`, `completed_step` | `404`; `409` finished/not retryable/limit used/stale not yet/claim lost, or version mismatch (saved as failed, not retryable); `503` store down |
   | Status | `GET /api/amenity-search/runs/{run_id}` | `200` + `status`, `completed_step`, `result` or `retryable`. First checks `app.state.r2_tasks`: a live task of this user's gives `running` with no database read | `404` (including another user's live task); `503` store down. A version mismatch reads as `200` `failed`, `retryable: false`, with no write |

   Run failures (`502`/`503`/`500` before Iteration 2) are saved on the row and reported by the status endpoint as `status: failed` with `retryable` (R2-C6 Iteration 2).
2. **Nested under the R1 run:** `POST /api/requirement-interpretation/runs/{r1_run_id}/amenity-search`.
3. **One generic endpoint for every service:** `POST /api/deep-search/runs?service=r2`.

### Critical Factors (from our context)
- **Independent invocability (Want):** R2 is its own service.
- **Consistency with R1.**
- **Each service has its own table and its own rules.**

### Reasoning
- **Approach 2** ties R2's address to R1 and suggests R2 is part of R1's resource, which works against independence. It also complicates R3, whose parent is R2.
- **Approach 3** merges three services with different inputs and rules into one contract.
- **Approach 1** is R1's shape, one router per service.

### Critical Decision Choices
- **General — status codes:** as in the table. A `running` run on retry that is not stale yet gets `409` with `status: running`.
- **Context-specific — refresh recovery:** the page stores `run_id` in `sessionStorage` as soon as the `202` arrives, and calls `GET`. While `status` is `running`, it polls `GET` every ~2 s, as with R3.

---

## R2-C8. Verification of R2-C1–C7

### Goal of Component
Evidence that the split, the resume and the guard work, and that R2's output is unchanged.

### Problem It Aims to Solve
A missing field after the split, a wrong resume point, a lost fence or a wrong `retryable` would only show up later in R3 or on the page.

**Traces to:** "without changing what either service computes", "must not repeat finished steps", "only one request at a time".

### Mandatory Sub-Tasks Independent of Approaches Taken
| Test | Passes when |
|---|---|
| Parity | The coordinator's step plan and a direct call of the three methods give the same final state for the same Places/Routes responses. |
| Resume parity | A failure injected in `enrichment`, then a retry, gives the same final state as a run that never failed. **Discovery is called once in total.** |
| No checkpoint after enrichment | After an injected failure in `attachment`, `completed_step` is still `discovery`. |
| Failed keeps checkpoint | "Save as failed" leaves `state` and `completed_step` unchanged. |
| Round trip | The initial, after-discovery and finished states, and the output, come back equal, including a saved fixture of real `Place.to_dict` data. |
| Version mismatch | Rejected as failed, not retryable. |
| Concurrent retries | Two retries sent at the same time against the fake store: exactly one runs, the other gets `409`. |
| Stale reclaim | A `running` row older than `stale_after` can be claimed; a fresh one can't. |
| Fencing | A write made with an old `attempts` changes nothing. |
| Retry limit | After one retry, a second failure is saved with `retryable: false`. |
| Retryable split | Each error in the R2-C6 table gives the listed `retryable`. |
| Ownership | Every read and write for another user's run finds nothing (coordinator, routes and fake store). RLS is not tested automatically (Iteration 1). |
| Migration | Not automated: checked by hand on the dev database when written (Iteration 1). |
| R1 finished output (R2-P1) | A finished R1 run returns its `category_metric_plans` from one read. A `running`, `needs_answers` or `failed` run, another user's run, and a run finished before the column existed all return `None` (`404`). The CHECK constraint is checked by hand on the dev database (Iteration 1). |
| Step rows (R2-C4 Iteration 1) | A clean run leaves `completed` rows for `discovery` and `enrichment` and none for `attachment`. A failure in `enrichment` leaves a `failed` row with the run's `retryable`; the retry moves it `started → completed`. A failure in `attachment`, then a retry, adds `enrichment` once. A lost fence adds no row. |
| Background lifecycle (R2-C6 Iteration 2) | Start and retry return `202` before discovery starts. A shutdown mid-run saves `failed` + `retryable`, before the shared clients close. `r2_tasks` is empty after completion. |
| E3 memory check (R2-C6 Iteration 2) | While a run's task is live, E3 answers `running` with no database read. Another user's `run_id` gets `404`, live or not. After the task ends, E3 reads the row and shows `finished` or `failed`. |
| HTTP | Each status code in R2-C7, including `401` without the cookie. |
| Regression | The existing R2 tests and sample runs pass after the state split. |

### Three Common Approaches
1. **Real providers and the real dev Supabase, with record/replay of provider responses, in `backend/tests_live/`.** R1's method, extended to the Places/Routes clients. (Chosen first; replaced by approach 2 in Iteration 1.)
2. **Fakes for the providers and the store, in `tests/` only. (Finalized, Iteration 1)**
3. **Contract tests at the HTTP layer only.**

### Critical Factors (from our context)
- **The output can't be reproduced** live, so parity needs fixed provider responses.
- **The guard is a database behavior:** the conditional update and the trigger can only be fully proven on Postgres.
- **Consistency with R1's C6.**
- **Cost and speed (Iteration 1):** the suite runs on every change, with no paid Places/Routes calls and no dev database.

### Reasoning
- **Approach 1** proves both the database rules and parity, but every run needs the dev Supabase and paid or recorded provider calls.
- **Approach 3** can't show *which* step reran.
- **Approach 2 (Iteration 1)** proves the coordinator's logic, the resume point, the retryable split and parity with fixed fake responses, fast and free. It can't prove the SQL itself (see Iteration 1).

### Critical Decision Choices
- **General — cost and time:** no test makes a paid Places/Routes call or touches a real database.
- **Context-specific — call counting:** the fake Places/Routes clients count calls per step, which is the evidence for "discovery runs once".

### Iteration 1 — Fakes in `tests/` Instead of Live Runs

**What changed.** R2-C8 moves from approach 1 (live providers + dev Supabase in `backend/tests_live/`) to approach 2: every R2 test runs in `backend/tests/` against fakes.

**The fakes**

- **Fake Places and Routes clients:** return fixed responses per request and count calls per step. They can raise any Google error (`PermissionDenied`, `ServiceUnavailable`, …) wrapped the way the real clients wrap it, so the config-error check (R2-C6 Iteration 1) is tested on the real `__cause__` chain.
- **Fake `R2RunStore` and fake `R1RunStore.get_finished_output`:** in-memory rows that apply the same rules as the SQL: the `user_id` filter, the `attempts = n` fence, the claim condition (failed ∧ retryable, or running ∧ stale), and "save as failed never touches `state`". A test clock drives `updated_at`, so stale reclaim is tested without waiting.
- **HTTP tests:** the FastAPI app with the fake store and fake clients injected into `app.state`, so status codes, the `202`, the task set and the E3 memory check are tested through real routes.

**What the tests still prove:** parity and resume parity (same fixed responses in, same final state out), the step plan and resume rule, the retryable split, fencing and the claim **logic**, the retry limit, the background lifecycle, the E3 memory check, ownership in the coordinator and the routes, the state round trip, and every HTTP code.

**What they no longer prove (risk accepted):**

- the real conditional UPDATE through supabase-py / PostgREST, including the `or_()` filter and timestamp format (traceflow A6);
- the `updated_at` trigger;
- RLS blocking the publishable key;
- the migrations being safe to re-run, and the `output` CHECK constraints on `r2_runs` and `r1_runs` (R2-P1);
- two real concurrent requests racing on Postgres.

The fake store can only show that the coordinator obeys these rules, not that the SQL enforces them. These are checked by hand on the dev database when the store and migrations are first written.

**Critical Decision Choices**

- **Context-specific — the fake store must mirror the SQL rules exactly:** if they drift, the tests pass while the real store doesn't. The fake keeps its filters next to a comment naming the SQL condition it copies.
- **Context-specific — test rows that depended on Postgres** (concurrent retries, stale reclaim, fencing, ownership/RLS, migration, R1 finished output) now run against the fakes and prove the logic only. RLS and migration have no automated test.

---

# R3. Specific Metric Resolution — Feature Process Flow

R3 takes a finished R2 run. For each discovered place whose category has `specific_metrics`, it finds the place's website, searches for evidence and resolves each metric. It needs **9 components**. R3's STEP 1–5 logic is reused exactly as it is. The only change inside the service is a resume point and a save hook in its one entry method (R3-C3).

## R3 Runtime Flow

1. The page sends `POST /api/specific-metric-resolution/runs` with `r2_run_id`. Any other field in the body gives `422`.
2. The login check verifies the user. The coordinator reads R2's **finished** output through `R2RunStore.get_finished_output(r2_run_id, user_id)`. A run that is missing, another user's, not finished, or saved under another R2 output version gives `404`.
3. The coordinator builds `SpecificMetricResolutionState(category_metric_plans, discovered_places, predefined_records)` from that output and creates the `r3_runs` row with `running`, `attempts = 0`, `completed_step = null` and this initial state saved.
4. The coordinator sets `run_id_var`, starts the background task and adds it to `app.state.r3_tasks` (keyed by `run_id`). The response is **`202 Accepted`** with `run_id` and `status: running` (R3-C7).
5. The background task builds a **fresh R3 instance with its own tool gateway** (R3-C2). The gateway takes its calls' slots from the **app-wide provider limits** built once at startup (R3-C2 Iteration 1). The task then calls `run_specific_metric_resolution(state, resume_after=None, on_step_completed=…)`.
6. Inside the method, unchanged: open the gateway, then **STEP 1** (plan index) and **STEP 2** (work items), which are cheap and always recomputed, then build the phase-1 catalog.
7. **STEP 3** (discovery batch: official-URL gate + website discovery). At its barrier the method awaits `on_step_completed("discovery_batch", state, breaker_open)`.
   - **Breaker closed:** the coordinator saves a checkpoint (`completed_step = "discovery_batch"`), then a `completed` `discovery_batch` row in `r3_run_steps` (R3-C5 Iteration 1).
   - **Breaker open:** no checkpoint (R3-C3). The coordinator writes a `degraded` `discovery_batch` row right away, with what STEP 3 found (R3-C5 Iteration 1).
8. **STEP 4** (one pipeline per amenity: phase-1 search loop + resolution turn) and **STEP 5** (sweep into `resolution_results` + the run-level raise) run unchanged.
9. The gateway closes (unchanged `finally`). The **finish write** saves the final state and output (`resolution_results`), sets `finished` and clears the failure fields. Then the `pipelines` step row is written as `completed`.
10. **On any failure,** the run is saved as `failed` with its stage, message and `retryable` flag. `state` and `completed_step` are left untouched. Then the step that was running gets a `failed` step row.
11. **Retry:** `POST /api/specific-metric-resolution/runs/{run_id}/retry` (no body).
    - The store claims the run in **one conditional update**: it must be `failed` and retryable, or `running` and stale. A losing request gets `409`.
    - The step rows from the resume step on that are `failed` or `degraded` are claimed (`→ started`).
    - On success the response is `202`. The background task resumes with `resume_after = completed_step`: STEP 1/2 are recomputed, STEP 3 is **skipped** if it was saved, and STEP 4 runs.
12. **Status:** `GET /api/specific-metric-resolution/runs/{run_id}` first checks `r3_tasks`. The user's own live run answers `running` with its `completed_step`, without reading the database. Otherwise it reads the row and returns `status`, `completed_step`, and `result` or `retryable`. The page polls it while the run is `running`.

## What Already Exists and Is Reused As-Is

| Built-in | Where | Used for |
|---|---|---|
| STEP 1–5 logic: plan index, work items, catalog, discovery batch, pipelines, sweep, run-level raise, circuit breaker | `SpecificMetricResolution` | Every value R3 produces |
| R3's typed errors | `MetricResolutionProviderError` (with `cause`), `MetricResolutionValidationError`, `McpConnectionError`, `McpToolUnavailableError` | Failure stage and the retryable split |
| `create_specific_metric_resolution` factory | `specific_metric_resolution.py` | Building one R3 instance per run (R3-C2) |
| R2 finished-output read | `R2RunStore.get_finished_output` (R2-C4) | R3's input |
| The guard, store layout, step table, status memory check and HTTP pattern | R2-C4 (and its Iteration 1), R2-C5, R2-C6 Iteration 2, R2-C7 (and R1) | Copied with R3's own tables, settings and step names |
| Per-gateway provider limits | `McpToolGateway._search_sem`, `_firecrawl_sem`, `_firecrawl_rate` ([mcp_tools.py:504](../../../clients/mcp_tools.py)) | Kept per run; the app-wide limits sit behind them (R3-C2 Iteration 1) |

## Component Order

```
R2-C1 ──► R3-C1 State split ──► R3-C3 Resumable entry + save points ─────────────────────────────┐
                 └──────────► R3-C4 Serialization ──► R3-C5 Run store ──► R3-C6 Single-execution guard ──► R3-C7 Coordinator (background) ──► R3-C8 HTTP endpoints
          R3-C2 Per-run R3 instance ─────────────────────────────────────────────────────────────┘
                                                                     R3-C9 Verification of C1–C8
```

---

## R3-C1. R3 State: Its Inputs and Its Own Outputs

### Goal of Component
R3 has a state object holding only the R2 handoff fields it reads, plus its own output fields, with the same names, types and defaults as today.

### Problem It Aims to Solve
R3's fields live inside R2's `AmenitySearchState`, so R3 can't be saved, loaded or resumed without carrying R2's state with it.

**Traces to:** "Each holds only the data it produces, plus the input it receives from the stage before it."

### Mandatory Sub-Tasks Independent of Approaches Taken
- `SpecificMetricResolutionState` has these fields:
  - **Inputs, copied from R2's output:** `category_metric_plans`, `discovered_places`, `predefined_records`.
  - **R3's own outputs, moved unchanged:** `website_search_results`, `discovery_search_results`, `official_gate_results`, `resolution_results`, `specific_records`, `amenity_records`.
- R3's method signatures change their annotation from `AmenitySearchState` to the new class. **No method body changes**, because every attribute read keeps its name.
- R3 tests, fakes (`_Step3OnlyService`) and sample runs build the new state.

### Three Common Approaches
Same three as R2-C1: **(1) two state classes with the same field definitions (Finalized)**, (2) one shared class with a projection at the store, (3) a wrapper around a frozen R2 output.

### Critical Factors (from our context)
- **Zero change to R3 method bodies:** R3 has about 2,000 lines whose state reads are spread across STEPs 1–5.
- **Clean ownership.**

### Reasoning
The reasoning is R2-C1's. R3 sharpens it: Approach 3 would rewrite reads in `_derive_work_items`, `_discovery_pre_pass`, `_run_discovery_batch` and `_run_amenity_pipelines`, which is the code the scope protects. Approach 1 changes annotations only.

### Critical Decision Choices
- **Context-specific — origin and radius are not in R3's state:** R3 never reads them (checked: no `state.origin` or `state.radius_km` in R3).
- **Context-specific — `resolution_results` is marked TEMPORARY** in the schema, to be replaced by `specific_records` and `amenity_records` when STEP 6 is built. All three move as they are. R3's output follows whichever is filled (R3-C5).

---

## R3-C2. One R3 Service Instance per Run (Prerequisite)

### Goal of Component
Two R3 runs at the same time never share a tool gateway, so one run closing its sessions can't break another.

### Problem It Aims to Solve
- **The gateway is shared today.** `SpecificMetricResolution` holds one `McpToolGateway`. `run_specific_metric_resolution` opens it at the start and **closes it in `finally`**.
- **`open()` won't start a second session.** It returns early when the gateway is already open, and `aclose()` stops the sessions for everyone.
- **So shared runs break each other.** With one app-wide instance (as R1 is built), run B finishing would close run A's MCP sessions in the middle of STEP 4. Today this never happens, because R3 is only called once per process. Over HTTP it would.

**Traces to:** "run … as two independent services. Each one is started, tracked and retried … on its own."

### Mandatory Sub-Tasks Independent of Approaches Taken
- The shared LLM caller is still injected (`owns_caller = False`) and closed once at shutdown.
- Each run's resources are closed when the run ends, whatever the outcome.

### Three Common Approaches
1. **Build a new `SpecificMetricResolution` (and so a new gateway) per run with `create_specific_metric_resolution`. (Finalized)** The app keeps the factory, not an instance.
2. **Make the gateway reference-counted:** the first `open()` starts the sessions, the last `aclose()` stops them, and runs share them.
3. **Allow one R3 run at a time** with a process-wide lock.

### Critical Factors (from our context)
- **No change to the gateway or R3's lifecycle code (Scope):** sessions are opened and closed per call today, by design (C3.1.1).
- **Independence between runs.**
- **Cost:** opening sessions per run is what happens today anyway.

### Reasoning
- **Approach 2** changes `McpToolGateway`'s lifecycle and its locking, which is tested code (C3.1.1).
- **Approach 3** makes one customer's run block every other customer's for minutes.
- **Approach 1** leaves both the gateway and R3 untouched, and costs the same session opening R3 already does on every call.

### Critical Decision Choices
- **Context-specific — rate limits are per gateway:** the Firecrawl token bucket and the search and Firecrawl semaphores are per instance. With one instance per run, two parallel runs could make twice the calls on the same provider account. Iteration 1 below adds one app-wide limit per provider behind them.
- **General — where the factory lives:** in `app.state`, built at startup from settings. The factory receives the app-wide provider limits and passes them into every gateway it builds.

### Iteration 1 — One App-Wide Limit per Provider, Behind the Per-Run Limits

**The problem.** Each run's gateway has its own limits: a Parallel search semaphore (`SEARCH_CONCURRENCY = 4`), a Firecrawl semaphore (`FIRECRAWL_CONCURRENCY = 2`) and a Firecrawl per-minute bucket (`FIRECRAWL_RATE_PER_MINUTE = 10`). The provider's limit is per account key, not per run. The code sizes Firecrawl's slots to the Free plan's 2 concurrent browsers. So two R3 runs at once can already have 4 Firecrawl calls in flight. Firecrawl answers `429`. The gateway backs off and retries. If it still fails, the amenity counts an `availability` failure. Enough of those open the circuit breaker, and the run fails.

**The fix.** One app-wide limit per provider, each set from that provider's plan as its own setting:

| Provider | App-wide limit | Setting (default) | Per-run limit (unchanged) |
|---|---|---|---|
| Parallel (`web_search`) | search slots | `R3_PARALLEL_SEARCH_CONCURRENCY` (10) | `SEARCH_CONCURRENCY` (4) |
| Firecrawl (map, scrape, `scrape_pages` fan-out, crawl) | Firecrawl slots | `R3_FIRECRAWL_CONCURRENCY` (2) | `FIRECRAWL_CONCURRENCY` (2) |
| Firecrawl | per-minute rate limiter | `R3_FIRECRAWL_RATE_PER_MINUTE` (10) | none: the app-wide limiter replaces the gateway's own |

- **Each call takes only its own provider's limits:** its run's slot first, then the app-wide slot. A Parallel search never touches a Firecrawl slot, so a full Firecrawl pool never slows Parallel. The gateway already keeps the two apart per run; this only makes each one shared app-wide.
- **The rate limiter is one per key:** a per-minute budget belongs to the account key, so a gateway given the app-wide limiter uses it in place of its own bucket. Keeping both would pace each call twice.
- **Order inside one call:** rate token (Firecrawl only), then run slot, then app-wide slot, then the per-call timeout and the call. Waiting for a token or a slot stays outside the call's timeout, as the token wait already does today. A run waiting on its own limit never holds an app-wide slot.

**Example.** With Parallel at 10 and Firecrawl at 2, Anna's and Ben's runs can have up to 10 searches in flight together (each run at most 4), while only 2 scrapes run at once across both runs.

**Mandatory sub-tasks**

- `McpToolGateway` takes three optional constructor arguments: the app-wide search semaphore, the app-wide Firecrawl semaphore and the app-wide Firecrawl rate limiter. Each one left out keeps today's behavior, so the C3.1.1 gateway tests pass unchanged.
- `_single_call` takes the app-wide slot inside the run slot. No retry, timeout, parsing or failure-kind logic changes.
- `lifespan` builds the three objects once from the three settings, and passes them to the R3 factory. Nothing closes them (they hold no connection).
- The three settings go in `src/core/config.py` and `.env.example`.

**Why this way**

- **The limit sits where the provider's limit is:** per provider, per key. That is what stops the self-made `429`s.
- **Runs stay independent:** each run keeps its own gateway, sessions and breaker (R3-C2 Approach 1). Only the slot counts are shared.
- **One process-wide cap on active runs is no longer needed:** it would make Ben wait for Anna's whole run, even while Anna is only waiting on the LLM.

**Critical Decision Choices**

- **Context-specific — scope exception:** the gateway's constructor and the slot order in `_single_call` change. Its sessions, retries, timeouts and failure kinds don't. This is the same kind of change R2-C2 Iteration 1 made to `AmenitySearch`.
- **Context-specific — LLM calls are not capped here:** they go through the shared LLM caller, not the gateway. This iteration covers the two web providers only.
- **Risk accepted:** when an app-wide pool is full, the wait makes STEP 3 and STEP 4 longer. That counts toward the stale cutoff (R3-C6), so R3-C9 records STEP 4 durations with two runs in parallel.
- **Risk accepted — one process:** the limits are per process. With several workers, each one has its own pool. That is fine at MVP (one process).

---

## R3-C3. Resumable R3 Entry Point and Persistence Points

### Goal of Component
`run_specific_metric_resolution` can start after a saved STEP 3, and it reports the end of STEP 3 so the coordinator can save it. Called as today, it behaves exactly as today.

### Problem It Aims to Solve
STEP 3 (LLM website selection + web searches for every declined amenity) is costly and non-reproducible, but it lives inside one method together with STEP 4. A failure in STEP 4 (for example the circuit breaker opening) would make a retry redo STEP 3.

**Traces to:** "keep the result of every step that is costly or non-reproducible, at the moment the whole step completes", "retried from the first unfinished step", "must not repeat finished steps".

### Mandatory Sub-Tasks Independent of Approaches Taken
- The step table, applying the persistence rule:

  | Step | Costly? | Non-reproducible? | Save after? |
  |---|---|---|---|
  | Gateway open + tool definitions | No (session start) | — | No: needed again by STEP 4 anyway |
  | STEP 1 plan index, STEP 2 work items | No | No: derived from saved inputs | **No**, always recomputed |
  | Phase-1 catalog build | No | No: built from tool definitions | **No**, always recomputed |
  | **STEP 3** discovery batch | Yes: an LLM selection turn + searches per declined amenity | Yes | **Yes**, a checkpoint `discovery_batch`, *unless the breaker is open* |
  | **STEP 4** pipelines + **STEP 5** sweep / run-level raise | Yes: the most expensive part | Yes | Covered by the **finish write**: after STEP 5 only the gateway close is left |
  | STEP 6 combine | Not built | — | — |

- **The degraded-step rule:** when the breaker is open at the end of STEP 3, every remaining amenity got `WebsiteSearchResult(None, "none")` because of the outage, not because no website exists. Saving that would make every retry run STEP 4 without websites. So STEP 3 is **not** saved as a checkpoint when `breaker_open` is true: `completed_step` stays null, and a retry reruns it. What it found is kept only as a `degraded` record row (R3-C5 Iteration 1).
- Defaults (`resume_after=None`, no callback) must give exactly today's behavior, so the existing R3 tests and sample runs pass without changes.
- On resume, STEP 1/2 and the catalog are recomputed from the saved inputs, which gives the same work items in the same order.

### Three Common Approaches
1. **Split R3 into public step methods that the coordinator calls in order** (as R2-C2 does). The coordinator opens and closes the gateway and passes the breaker into each step.
2. **Keep the single entry and add `resume_after` + an awaited `on_step_completed(step, state, breaker_open)` callback. (Finalized)** The method skips STEP 3 when `resume_after == "discovery_batch"`, and otherwise awaits the callback at STEP 3's barrier. Everything else in the method is unchanged.
3. **State-inferred skip:** skip STEP 3 when `state.website_search_results` already has a verdict for every work item.

### Critical Factors (from our context)
- **Run-scoped resources:** the gateway session and the **one circuit breaker per run** (R3.M1.5) are created inside the method and shared by STEP 3 and STEP 4. That is exactly where R3 differs from R2.
- **Zero change to decision logic:** the barrier order, the `finally` close and the breaker's sharing must stay.
- **Exact resume position,** and **don't save degraded output.**

### Reasoning
- **Approach 1** suits R2, which has no run-scoped resources. For R3 it moves the gateway lifecycle and the breaker out of the service into the coordinator. That rewrites the method the scope protects, and the coordinator would have to know R3 internals (`_CircuitBreaker`, the raw tool definitions).
- **Approach 3** can't tell a saved STEP 3 from one that was cut short. It also can't see that the verdicts are degraded, so it would happily resume on outage-made `none` verdicts.
- **Approach 2** adds two optional parameters and one awaited call at the existing barrier, so the session, the breaker and the error handling stay where they are. The `breaker_open` flag lets the coordinator apply the degraded-step rule without the service knowing anything about persistence.

### Critical Decision Choices
- **General — callback errors:** if the checkpoint save raises (store down, or a lost fence → `RunSupersededError`), the error leaves the method through its existing `finally`, so the gateway still closes. The coordinator then handles it like any failure.
- **Context-specific — the breaker on resume:** a resumed run starts with a **fresh breaker** (same threshold). The previous attempt's failure count doesn't carry over. This matches today's "one breaker per run" rule, with a retry treated as a new execution.
- **Context-specific — the internal `run_id = uuid4().hex` in STEP 4:** kept as it is. Log lines are tied to the HTTP run through `run_id_var`. The coordinator sets it **before** `create_task`, so the task's context carries it into every log line (as R2).
- **Context-specific — no work items:** STEP 3 runs on an empty list and is saved, STEP 4 is skipped (the catalog is `None`), and the run finishes with empty results. This is unchanged behavior.

---

## R3-C4. R3 State Serialization (Tuple Keys)

### Goal of Component
A saved R3 state turns into JSON and back with nothing lost, including the four dicts keyed by `(category_id, place_id)`.

### Problem It Aims to Solve
`website_search_results`, `discovery_search_results`, `official_gate_results` and `resolution_results` are `dict[tuple[int, str], …]`. **Tested in a scratch script (Pydantic 2.13):** R1's `TypeAdapter` method dumps the key `(1, "a,b")` as the string `"1,a,b"`, and loading it back **fails** (`Input should be a valid tuple`). Joining the parts with a comma isn't safe either, because place IDs are opaque strings.

**Traces to:** "the saved results it builds on must load back unchanged."

### Mandatory Sub-Tasks Independent of Approaches Taken
- Round-trip tests for the initial, after-STEP-3 and finished states, including keys whose `place_id` contains `,`. The initial state is built from a **real R2 output** loaded through R2's output codec, not a hand-made one. A real capture is what caught R2's `price_level` annotation mismatch (`int` from Places, annotated `str`); R3 carries the same `predefined_records`.
- A version envelope with `R3_STATE_SCHEMA_VERSION`. A mismatch means failed, not retryable.
- The step-row outputs (R3-C5 Iteration 1) use the same tuple-key encoding inside R1's step envelope `{"schema_version", "data"}`.

### Three Common Approaches
1. **`TypeAdapter` for values, with key encoding at the store boundary. (Finalized)** Each tuple-keyed dict is written as a list of `{"category_id": int, "place_id": str, "value": {…}}` entries and rebuilt into the dict on load. The state class is untouched.
2. **Annotated serializers on the state fields:** `Annotated[dict[tuple[int, str], X], PlainSerializer(...), BeforeValidator(...)]` in `schemas.py`. The runtime type stays the same, but the schema definitions change.
3. **Change the fields to nested dicts:** `dict[int, dict[str, X]]`, like R2's.

### Critical Factors (from our context)
- **Don't change the objects in state (Scope).**
- **Exact round trip** (proven failing today).
- **One place that knows the storage format:** the store, as in R1.

### Reasoning
- **Approach 3** is the cleanest design from scratch, but it changes the state's types and every read in R3, which is out of scope.
- **Approach 2** keeps the types, but puts storage concerns into the schema file the scope protects, so every reader of the schema sees them.
- **Approach 1** keeps the storage format inside the R3 store next to the version envelope, so the classes stay untouched.

### Critical Decision Choices
- **Context-specific — list order:** entries are written in dict insertion order and rebuilt in the same order, so log-order-sensitive code behaves the same after a resume.
- **General — the output uses the same encoding:** `resolution_results` → a list of `{category_id, place_id, value}`, so the page gets plain JSON.

---

## R3-C5. R3 Run Store (`r3_runs`)

### Goal of Component
Each R3 run is one row tied to its user and its R2 run, with the same operations as R2-C4.

### Problem It Aims to Solve
R3 has no table and no write path.

**Traces to:** as R2-C4.

### Mandatory Sub-Tasks Independent of Approaches Taken
- A migration `<ts>_create_r3_runs.sql` with R2-C4's columns, with `r2_run_id` referencing `r2_runs` (`on delete cascade`) in place of `r1_run_id`. It is safe to re-run, has RLS on with no policies, and has the `updated_at` trigger.
- `completed_step` is checked `in ('discovery_batch')` or null.
- `R3RunStore` in `r3_run_store.py` with R2-C4's seven operations, the `user_id` filter on every query, and the fencing filter on every write after the claim.
- "Save as failed" never touches `state` or `completed_step`.
- "Save as finished" sets `failure_stage` and `failure_message` back to null, so a run that finishes on its retry doesn't still show the first attempt's failure (found in R2's build).

### Three Common Approaches
Same three as R2-C4: **(1) one row with the versioned state blob + `completed_step` (Finalized)**, (2) a run row + a step-output table, (3) a column per step output. Iteration 1 below adds a step table next to approach 1 as a record only, as R2-C4 Iteration 1 does; the run row still decides everything.

### Critical Factors (from our context)
- **One mid-run checkpoint** (STEP 3) plus the finish write.
- **R3's state is the largest one,** because it carries R2's places and records plus evidence, so each rewrite is bigger.
- **Consistency with R1 and R2.**

### Reasoning
State size is the only factor that could favor Approach 2 (write only the step's own output). With two writes per run, rewriting the whole state twice is still cheap, and Approach 1 keeps R3 identical to R1 and R2.

### Critical Decision Choices
- **Context-specific — what `output` holds:** `resolution_results` (encoded as in R3-C4) while STEP 6 is unbuilt. When STEP 6 lands, the output switches to `amenity_records`, with a version bump.
- **Context-specific — Places content:** R3's state carries `predefined_records` (Places content), so the retention decision in R2-C4 applies here too: kept for now, with the policy decided in a later phase.

### Iteration 1 — A Step Table `r3_run_steps`, with a `degraded` Status

**What changed.** R3 gets a second table, `r3_run_steps`, with one record row for each of its two expensive steps, filled the way `r2_run_steps` is. `r3_runs` keeps `state`, `completed_step`, `output`, the failure columns, `retryable`, `attempts` and fencing, and **`r3_runs` alone decides where a retry resumes**. The step table is a record next to it, not a second source of truth.

**The table** (migration `<ts>_create_r3_run_steps.sql`, safe to re-run, copied from `create_r2_run_steps.sql`):

- `run_id` (references `r3_runs`, `on delete cascade`), `step_id`, `status`, `output`, `error_type`, `error_message`, `retryable`, `created_at`;
- primary key `(run_id, step_id)`;
- `step_id` in (`discovery_batch`, `pipelines`): STEP 3 (finding websites) and STEP 4 (resolving metrics). STEP 1/2, the catalog and STEP 5 are recomputed or covered by the finish write, so they have no row;
- `status` in (`started`, `completed`, `degraded`, `failed`). `degraded` is R3's addition;
- the checks `(status in ('completed', 'degraded')) = (output is not null)` and `(status = 'failed') = (error_type is not null and retryable is not null)`. A `degraded` row may hold data; in R2 only `completed` rows can;
- `output` in the step envelope `{"schema_version", "data"}`, tuple keys encoded as in R3-C4: STEP 3's three result dicts (`official_gate_results`, `discovery_search_results`, `website_search_results`) for `discovery_batch`, and `resolution_results` for `pipelines`;
- RLS on with no policies, and a trigger that rejects any change to a `completed` row.

**How it is filled**

| Operation | R3 use |
|---|---|
| `insert_step` (new `completed` row; a duplicate key means another execution) | `discovery_batch` right after the checkpoint write succeeds (breaker closed). `pipelines` right after the finish write succeeds. |
| `save_step_degraded` (new `degraded` row with output, or `started → degraded` on a claimed step) | `discovery_batch` when STEP 3 ended with the breaker open. Written right away at the STEP 3 barrier. |
| `save_step_failed` (new `failed` row, or `started → failed` on a claimed step) | The step that was running when the run failed gets a `failed` row with `error_type`, `error_message` and the same `retryable` as the run. |
| `claim_step` (`failed` or `degraded` → `started`, error and output cleared, as the check requires) | After the run claim (R3-C6) wins: every `failed` or `degraded` row at or after the resume step. |
| `complete_claimed_step` (`started → completed` with the new output) | At the step's write point: the checkpoint for `discovery_batch`, the finish write for `pipelines`. |

**The `discovery_batch` row's life when searches fail:**

1. **First run, breaker open at STEP 3:** no checkpoint, so `completed_step` stays null. The row is saved as `degraded`, with what STEP 3 found.
2. **Retry claims it:** `degraded` becomes `started`, the same way a `failed` row is claimed.
3. **STEP 3 succeeds on the retry:** the checkpoint is saved, and `started` becomes `completed` with the new results. (If the breaker opens again, the row goes `started → degraded` with the new results.)

**Write order.** The `r3_runs` write goes first, fenced. The step row follows only when that write matched. So:

- a lost fence writes no step row;
- a duplicate step row or a claimed row that moved is logged (`r3_run.step_conflict`) and stops the execution, as R2 does;
- a store failure on the step row is logged only. The run row is already right, so the run carries on.

**Which step was running.** The method has one entry, so the coordinator tracks the step from the callback:

- **Before the STEP 3 callback:** a gateway, capability or catalog error (`McpConnectionError`, `McpToolUnavailableError`, `MetricResolutionValidationError`) happens before STEP 3 and writes no step row. Any other error is recorded on `discovery_batch`.
- **After the callback, or on a resume that skipped STEP 3:** an error is recorded on `pipelines`.

**Why the `degraded` row is written right away.** A breaker-open STEP 3 writes nothing to `r3_runs`, so this one step row is not preceded by a fenced run write. It could only clash with a newer execution's row if a live STEP 3 ran past `stale_after` (30 min) and the user retried in that window. That isn't realistic at MVP (one process, STEP 3 takes minutes), so the row is written at once, like a completed STEP 3 row.

**Why `pipelines`' row waits for the finish write.** A completed row can never change. STEP 5's run-level raise comes after STEP 4. If `pipelines` were recorded as soon as STEP 4 returned and STEP 5 then raised, a retry would rerun STEP 4 (the resume point is still `discovery_batch`) and collide with its own completed row.

**Mandatory sub-tasks**

- `R3RunStore` adds `insert_step`, `save_step_degraded`, `save_step_failed`, `claim_step` and `complete_claimed_step`.
- `load_run` reads the run with its step rows embedded, as R2's does, and fails loudly if the embed is missing.
- The coordinator calls them at the points in the table above. The step plan, the resume rule and the retryable split don't change.
- R3-C9 adds the step-table tests.

**Critical Decision Choices**

- **Context-specific — the run row stays the truth:** resume uses `completed_step`, and status uses `r3_runs.status`. A `degraded` row never moves the resume point. If a crash lands between the run write and the step write, the step row is missing. That gap is in the record only.
- **Context-specific — a `completed` row still never changes:** only `started`, `failed` and `degraded` rows move.
- **Context-specific — the same data is stored twice:** STEP 3's results are in `state` and in the `discovery_batch` row, and `resolution_results` is in the final `state`, in `output` and in the `pipelines` row. R3's state is the largest, so this costs more than in R2. Accepted for consistency with R1 and R2. The Places content rule above covers this table too.
- **Context-specific — a crashed run has no `failed` row:** a stale `running` run that is reclaimed has nothing to claim, so the resumed step is inserted as a new row.
- **Context-specific — a claimed row the retry never reaches stays `started`:** for example, the retry fails at gateway open before STEP 3. The table is a record only, and the run is not retryable after its one retry. Accepted, as R2 accepts it for a claimed `enrichment` row.
- **Context-specific — atomicity:** the run write and the step write are separate statements (PostgREST has no transaction across them). The write order above keeps the run row correct whichever one fails.

---

## R3-C6. Single-Execution Guard

### Goal of Component
As R2-C5: one live execution per run, crash recovery, and fencing.

### Problem It Aims to Solve
As R2-C5, with more at stake. R3 runs for minutes in a background task (R3-C7), so the window for duplicate retries and restarts is much larger.

**Traces to:** "retried by only one request at a time, even when the same retry arrives more than once at once."

### Mandatory Sub-Tasks Independent of Approaches Taken
- **One conditional update decides the claim:** failed + retryable at `attempts = n`, **or** running + stale at `attempts = n` → running, `attempts = n + 1`.
- Fencing on every later write. `MAX_RETRY_ATTEMPTS = 1`.

### Three Common Approaches
Same three as R2-C5: (1) R1's guard as-is, **(2) `running` + stale-after + `attempts` fencing (Finalized)**, (3) a heartbeat lease.

### Critical Factors (from our context)
- **Long STEP 4 with no write in it,** so `updated_at` doesn't move for minutes. `stale_after` has to cover it.
- **Recovery delay is acceptable** (long-running agent).
- **Simplicity.**

### Reasoning
The heartbeat lease (Approach 3) is the strongest fit for long steps, and R3 is where it would be most justified. Approach 2 is still chosen:
- **Clean shutdowns don't wait:** a deploy or restart cancels the background task, which saves the run as failed and retryable at once (R3-C7).
- **Only hard crashes wait:** they wait for `stale_after`, which is acceptable for a rare event.
- **Fencing makes a too-small `stale_after` safe:** a late original can't overwrite the retry's results.

**Revisit trigger:** if live runs show STEP 4 regularly approaching `stale_after`, switch to Approach 3.

### Critical Decision Choices
- **Context-specific — `stale_after` for R3:** **30 minutes**, as the setting `r3_stale_after_seconds` (`R3_STALE_AFTER_SECONDS`, default 1800, `gt=0`) in `src/core/config.py`, with a commented entry in `.env.example`. It must be longer than the longest STEP 4 seen in live runs, including time spent waiting for the app-wide provider limits (R3-C2 Iteration 1); the verification records STEP 4 durations to check this.

---

## R3-C7. R3 Run Coordinator (Background Execution)

### Goal of Component
One service runs R3 around the store:
- **Start:** load R2's output → create the row → return `202` → in the background, build a per-run R3 instance → run with the save callback → finish.
- **Retry:** claim → `202` → run in the background with `resume_after = completed_step`.

Any R3 error saves the run as failed with its stage and `retryable` flag.

### Problem It Aims to Solve
R3 takes minutes, which is longer than typical proxy and browser request timeouts. Run inside the request, as R1 is, most R3 runs would end with the customer seeing a timeout while the server is still working.

**Traces to:** "started, tracked and retried … on its own", "retried from the first unfinished step", "tell retryable failures from non-retryable ones".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **Retryable split:**

  Every "Yes" below means `retryable = attempts < MAX_RETRY_ATTEMPTS` (1), so a failure on the retry itself is never retryable.

  | Error | Stage | Retryable | Why |
  |---|---|---|---|
  | `MetricResolutionProviderError` at run level (`cause`: `availability`, `circuit_open`, `content`) | `exc.stage` | Yes | Provider failure; later calls may succeed |
  | `McpConnectionError` (gateway can't connect), no config cause | `exc.stage` | Yes | Transient |
  | `McpConnectionError` whose cause is a refused key (Iteration 1) | `exc.stage` | No, log `r3_run.config_error` | The key is wrong; it fails again |
  | `MetricResolutionValidationError` (catalog can't be built) | `exc.stage` | No | The gateway schema doesn't match; it fails again |
  | `McpToolUnavailableError` (a required tool is missing) | `exc.stage` | No | Configuration; it fails again |
  | `RunStoreError` on the STEP 3 checkpoint or the finish write | `run_store` | Yes | A database blip: the work since the last save is lost, the run is not (as R2's D-R2-3). If the failed write fails too, it is logged (`r3_run.failed_not_saved`) and the row stays `running`, reclaimable after `stale_after` |
  | `StateVersionMismatchError` | `load_state` | No | Start again |
  | `RunSupersededError` (lost fence) | — | Not saved | A newer execution owns the row |
  | Any other exception | `unexpected` | No, `logger.exception` | A bug |
  | Cancellation (shutdown) | `cancelled` | Yes | Best-effort save as failed, then re-raise |

- `R3_STAGE_ERRORS` / `R3_PROVIDER_ERRORS` tuples in `src/exceptions/deep_search.py`, and `RunStoreError`'s docstring widened to cover `r3_runs`. No `R3RunFailedError`: since the run is a background task, a failure never reaches a controller. It is saved on the row and read through status, so nothing would catch such an error (as R2's decision D-R2-5).
- **The R2 input saved under another version:** `R2RunStore.get_finished_output` raises `StateVersionMismatchError`. Start answers `404` and logs `reason=r2_version_mismatch`, before any row exists (as R2 does for R1's output).
- `run_id_var` is set **before** `create_task`, so the task's context carries the HTTP run ID into every R3 log line.
- The per-run R3 instance (R3-C2) is closed in the task's `finally`.

### Three Common Approaches
1. **Run inside the request,** as R1 does (and R2 did before R2-C6 Iteration 2).
2. **`202 Accepted` + an in-process background task (`asyncio.create_task`) + status polling. (Finalized for R3)**
3. **An external job queue and worker** (arq/Redis, or Celery).

### Critical Factors (from our context)
- **Run length is minutes** (Environment b: "requests time out").
- **Crash recovery** is already handled by R3-C6.
- **Proportionate simplicity:** no queue infrastructure exists.
- **Consistency with R1** in endpoints, store and error bodies, if not in timing.

### Reasoning
- **Approach 1** is right for R1 (seconds), but for R3 it turns normal runs into client timeouts.
- **Approach 3** gives the strongest isolation, but its main benefit, surviving process loss, is already covered by the stale reclaim and the step checkpoint, and it adds Redis and a worker deployment.
- **Approach 2** needs only the status endpoint R1 already has, and fits the existing single FastAPI process.

### Critical Decision Choices
- **General — keeping tasks alive:** tasks are held in `app.state.r3_tasks`, so they aren't garbage-collected, and removed when done. Iteration 2 makes it a dict keyed by `run_id`, for the status check.
- **General — shutdown:** `lifespan` cancels the running R3 tasks and awaits them, with R3's own timeout `R3_SHUTDOWN_TIMEOUT_SECONDS = 10`. Each task saves its run as failed with `retryable = attempts < MAX` on `CancelledError`, then re-raises.
  - **Order:** the R3 tasks are cancelled and awaited **before** the shared LLM caller and the database client close. A cancelled task still needs the database for its failed write, and may still be inside an LLM call. The app-wide provider limits (R3-C2 Iteration 1) need no closing.
  - **Why R3's timeout is longer than R2's 5 s:** on cancel, the method's unchanged `finally` closes the run's MCP gateway (two sessions) **before** the coordinator's failed write. The gateway close spends part of the timeout.
  - **Timeout hit:** log `r3_run.shutdown_timeout` (WARN) with the pending run IDs. Those rows stay `running` and are reclaimable after `stale_after` (R3-C6).
- **Context-specific — the input must be the same user's finished R2 run:** checked before the row is created, so a bad `r2_run_id` gets `404` (missing, another user's, not finished, or another R2 output version; no `409` path, as in R2-C6) and no run is created.
- **Context-specific — this departs from R1:** the start and retry responses are `202` with `status: running`, not a result. The page polls `GET` (or uses refresh recovery) to see the result.

### Iteration 1 — Config Errors Are Not Retryable (gateway open)

**The problem.** A refused Firecrawl or Parallel key fails the gateway open as `McpConnectionError`, which the split above marks retryable. The customer gets a Retry button that can't work, uses up the one retry, and then hits "Start again", which fails the same way.

**What the code keeps.** The gateway raises `McpConnectionError(...) from self._start_error` when a session can't open, and `_start_sessions` raises it `from` the first failure. So the original error stays on `__cause__`:

```
McpConnectionError (stage "open")     ← what the coordinator sees
  └─ __cause__: the session's start error
       └─ (possibly inside an exception group) HTTP status error 401 / 403   ← the real reason
```

**The fix.** One helper in the coordinator, `is_config_error(exc)`, follows `__cause__` (and the members of an exception group) with a depth limit of 8 links, and looks for an HTTP status of `401` or `403` on the error or its `response`.

- **Found:** save the run with `retryable = false` and log `r3_run.config_error` (ERROR, with the server name and status).
- **Not found:** keep the table's rule (retryable while `attempts < MAX`).

**Mandatory sub-tasks**

- The coordinator calls the helper only for `McpConnectionError`, before applying the table.
- R3-C9 adds two tests: a `401` under `McpConnectionError` gives `retryable: false` and one `r3_run.config_error` log; a connection timeout still gives `retryable: true`.

**Why this way**

- **R3's code and the gateway stay unchanged:** only the coordinator's decision changes, as in R2-C6 Iteration 1.
- **It covers the case where R3 can tell:** the cause chain is intact only at gateway open.

**Critical Decision Choices**

- **Context-specific — a refused LLM key is not covered (open):** the LLM provider adapters map `AuthenticationError` / `PermissionDeniedError` to `failure_class = "availability"` (`llm_provider.py`). By the time a run fails, STEP 5's run-level raise is a new error built from the per-item records, so the original cause is gone. A fix would change the shared LLM client's failure classes, which R1 uses and R3's breaker reads, and that is out of scope here. **Risk accepted for now:** this only happens when every provider in the chain refuses its key, and it costs one useless retry. Tracked as traceflow B25.
- **Context-specific — `429` stays retryable:** a rate limit recovers by the time the customer clicks Retry.
- **Risk accepted:** the `401` shape from the hosted Firecrawl endpoint is not confirmed live (the `mcp.py` docstring says so). If the status isn't on the chain, the run falls back to "retryable". The live check is in R3-C9.

### Iteration 2 — Status Answers Live Runs from Memory

**The problem.** The page polls status every few seconds for a run that takes minutes, so one run is polled tens of times. Each poll reads `r3_runs`, even though this process already knows the run is alive.

**The fix.** `app.state.r3_tasks` becomes a dict keyed by `run_id`. Each entry holds `(task, user_id, completed_step)`. Status checks it before the database:

- **Found, same `user_id`:** `200 {run_id, status: "running", completed_step}` with no database read.
- **Found, another user's:** `404`, the same answer the database read would give.
- **Not found:** the database read as before (finished, failed, crashed, or a run owned by another process).

**Mandatory sub-tasks**

- **The entry's `completed_step`:** set at scheduling from the row (null on start, the row's value on retry). It is updated to `discovery_batch` only after the STEP 3 checkpoint write matched. So the memory reply never shows a step the row doesn't have. R3's progress screen needs it ("finding websites" vs "resolving metrics").
- **Removal:** the done callback removes the entry only if it still holds this task (a reclaimed run may have a newer entry). It also logs `r3_run.task_crashed` (ERROR) if the task ended with an exception other than a cancel.
- **Order:** the task saves its final status before the done callback removes it, so a poll never sees "not in memory" while the row still says `running` for a live run.
- R3-C9 adds a memory-check test.

**Critical Decision Choices**

- **Context-specific — the memory check is per process:** a run started by another worker isn't in this process's dict, so status falls back to the database. That is correct, only slower. At MVP there is one process.
- **Still open — B5:** a crashed run is gone from memory and reads as `running` from the row until it is stale (30 min). At one process, "`running` in the row but not in memory" means the run crashed. Status could report it as retryable, but that breaks with several workers, so it is not decided here.

---

## R3-C8. R3 HTTP Endpoints

### Goal of Component
The page starts, retries and polls R3 over HTTPS behind the login check, with R1's body shapes.

### Problem It Aims to Solve
No R3 routes exist, and app startup doesn't build R3's factory, store, coordinator or task set.

**Traces to:** "started, tracked and retried for a specific user", "behave like R1 in how they … report status … and handle retries".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **Startup:** at app startup (`lifespan`), build the three app-wide provider limits (R3-C2 Iteration 1), the R3 factory (with the shared caller and those limits), `R3RunStore` (on the existing database client), the coordinator and the task dict (`app.state.r3_tasks`). With no service-role key, give `503`, as R1 does.
- **Shutdown:** `coordinator.shutdown()` first, then the shared LLM caller, then the database client (R3-C7 "shutdown"). R3's shutdown is independent of R2's: each coordinator is shut down before any resource they share closes.
- **Layers:** a dependency, routes and controllers split, as in R1.
- **Models:** `StartSpecificMetricResolutionRequest { r2_run_id: UUID }` with extra fields forbidden (any other field gives `422`), and a response with `run_id`, `status`, `completed_step`, `result` and `retryable`. The app-wide `422` handler (built with R2) already turns a non-finite number in a body into a `422`, not a `500`.
- **Wiring:** register the router and add a Swagger tag.

### Three Common Approaches
1. **Separate action endpoints under `/api/specific-metric-resolution/runs`, mirroring R1. (Finalized)**

   | Purpose | Method and path | Success | Errors |
   |---|---|---|---|
   | Start | `POST /api/specific-metric-resolution/runs` | `202` + `run_id`, `status: running` | `404` R2 run not found or not finished; `503` store down |
   | Retry | `POST /api/specific-metric-resolution/runs/{run_id}/retry` (no body) | `202` + `status: running` | `404`; `409` not failed/not retryable/claim lost/still running and not stale |
   | Status | `GET /api/specific-metric-resolution/runs/{run_id}` | `200` + `status`, `completed_step`, and `result` (finished) or `retryable` (failed) | `404`; `503` store down |
2. **Nested under the R2 run:** `POST /api/amenity-search/runs/{r2_run_id}/specific-metric-resolution`.
3. **A streaming endpoint** (Server-Sent Events) that holds the connection open and pushes step events.

### Critical Factors (from our context)
- **Independence (Want)** and **consistency with R1 and R2.**
- **Background execution** (R3-C7) needs a way to report progress.
- **Connections drop** (Environment b).

### Reasoning
- **Approach 3** gives live progress, but it relies on a long-held connection, which is the thing the environment says drops. It still needs `GET` as a fallback.
- **Approach 2** couples R3 to R2's resource, as in R2-C7.
- **Approach 1** with polling `GET` survives drops by design, and matches R1's and R2's shape.

### Critical Decision Choices
- **General — where provider failures show up:** R3's provider failures are not returned by start or retry (they return before the run ends). They show up in `GET` as `status: failed` with `retryable`. `502`/`503` are not used by R3's action endpoints.
- **Context-specific — poll interval:** the page polls every few seconds while `status` is `running`. `completed_step` lets it show "websites found, resolving metrics".

---

## R3-C9. Verification of R3-C1–C8

### Goal of Component
Evidence that R3's output is unchanged, that the resume skips a saved STEP 3, that a degraded STEP 3 is never a checkpoint, that parallel runs stay within each provider's limit, and that the guard holds under background execution.

### Problem It Aims to Solve
R3 is the costliest and least reproducible service, so a wrong resume point or a lost fence costs money and silently changes results.

**Traces to:** "without changing what either service computes", "must not repeat finished steps", "only one request at a time", "load back unchanged".

### Mandatory Sub-Tasks Independent of Approaches Taken

**With fakes** (`backend/tests/`: a fake gateway with call counts and app-wide-limit tracking, a fake `R3RunStore` that applies the SQL rules, a fake `R2RunStore.get_finished_output`, a test clock):

| Test | Passes when |
|---|---|
| Default parity | Calling `run_specific_metric_resolution(state)` with no new arguments gives the same result as before the change. The existing R3 suites pass unchanged, apart from the state class. |
| Resume parity | A failure injected in STEP 4, then a retry, gives the same final state as a run that never failed, with the same fixed provider responses. **STEP 3 provider calls are made once in total.** |
| Degraded STEP 3 not checkpointed | With the breaker forced open during STEP 3, no checkpoint is written (`completed_step` null), and a retry reruns STEP 3. |
| Breaker on resume | A resumed run starts with a closed breaker. |
| Tuple-key round trip | The four keyed dicts come back equal, including a `place_id` containing `,`, in the same order. The initial state is built from a real R2 output capture. |
| Per-run instance | Two R3 runs at the same time: one finishing doesn't close the other's gateway. |
| App-wide provider limits | With two or more runs at once: Parallel calls in flight never exceed 10 (and 4 per run), Firecrawl calls never exceed 2, Firecrawl call starts stay within the per-minute limit, and a full Firecrawl pool doesn't delay a Parallel call. With no limits passed, the gateway behaves as today. |
| Step rows | Clean run: `completed` `discovery_batch` + `pipelines`. Breaker open in STEP 3: a `degraded` `discovery_batch` row with data and a `failed` `pipelines` row. A retry moves both to `started`, then `completed` on success. A STEP 5 raise leaves no `completed` `pipelines` row. A lost fence adds no row. A gateway-open failure adds no row. |
| Background lifecycle | Start returns `202` before STEP 1. A shutdown mid-run saves `failed` + `retryable` before the shared LLM caller and the fake database close. The task dict is empty after completion. |
| Status memory check | While a task is live, status answers `running` with its `completed_step` and no store read; `completed_step` changes only after the checkpoint write. Another user's ID gets `404`. After the task ends, status reads the row. |
| Concurrent retries / stale reclaim / fencing / retry limit | The same checks as R2-C8, against the fake store's rules. |
| Retryable split | Each error in the R3-C7 table gives the listed stage and `retryable`. A `401` under `McpConnectionError` gives `retryable: false` and one `r3_run.config_error`; a connection timeout gives `retryable: true`. A `RunStoreError` on the checkpoint saves stage `run_store`, retryable. |
| Ownership and HTTP codes | Through the real routes with the fakes injected: another user's run is `404` on all three endpoints; `401`, `422` (bad `r2_run_id`, extra field), `404` (incl. an R2 version mismatch), `202`, `409`, `503` all hold. |

**By hand on the dev Supabase** (when the store and migrations are first written): re-running both migrations changes nothing; RLS blocks the publishable key; the `updated_at` trigger moves on update; the completed-immutable trigger rejects a change; `degraded` rows accept output and `started` rows don't; one `claim_retry` on a stale and a fresh row proves the OR filter and timestamp format (as A6).

**Live, kept small:**

| Test | Passes when |
|---|---|
| Recorded parity | A recorded live run, replayed, gives the same final state with and without a STEP 4 failure plus retry. |
| STEP 4 duration | Recorded on live runs, alone and with two runs in parallel (app-wide limits in play), to confirm `stale_after` (R3-C6). |
| Firecrawl `401` shape | A run with a wrong Firecrawl key ends `failed`, `retryable: false` (R3-C7 Iteration 1). |

### Three Common Approaches
The three listed in R2-C8: (1) real providers + dev Supabase with record/replay, (2) fakes only, (3) HTTP contract tests only. **R3 uses approach 2 for all logic, plus small live runs for what only live runs show (Finalized, following R2-C8 Iteration 1).**

### Critical Factors (from our context)
- **LLM and web output vary per call,** so parity needs fixed or replayed responses.
- **A live STEP 4 is expensive,** so the tests must keep live runs to a few amenities.
- **Real STEP 4 durations** set `stale_after`, and only live runs show them.

### Reasoning
- **Approach 1 for everything** would run the guard, lifecycle and HTTP tests against the dev database and live providers: slow, costly, and dependent on network and keys. R2 found that its fakes prove the same logic.
- **Approach 2 alone** can't prove the conditional update, the triggers, RLS or the migration, and can't show real STEP 4 durations.
- **Approach 3** can't show *which* step reran.
- **Approach 2 + small live runs + a manual database check** proves the logic on every run of the test suite, and checks the SQL and the durations where they actually live.

### Critical Decision Choices
- **Context-specific — the fake store must mirror the SQL rules exactly:** if they drift, the tests pass while the real store doesn't. The fake keeps its filters next to a comment naming the SQL condition it copies (as R2).
- **Context-specific — keep live runs small:** use one or two categories with specific metrics and three places each, so a live run stays within a few minutes and a small token budget.
- **General — existing fakes stay for decision logic:** the fake-gateway suites (`test_r3_m1_3_*`, `test_r3_m1_4_*`, `test_r3_m2_2_*`) keep covering it.
- **Risk accepted:** the SQL rules (conditional update, triggers, RLS, migrations) have no automated test, as in R2.

---

# Review Check (R2 and R3)

- **Order:**
  - **R2:** C1 → C2 and C3; C3 → C4 → C5; C2 + C5 → C6 → C7; C8 covers all.
  - **R3:** R2-C1 → R3-C1 → C3 and C4; C4 → C5 → C6; C2 + C3 + C6 → C7 → C8; C9 covers all.
  - No component is unconnected.
- **Approaches are real alternatives:** each one listed would meet its component's goal on its own. Mandatory work (fencing, `user_id` filters, version envelopes, round-trip tests) sits under Mandatory Sub-Tasks, not among the approaches.
- **Where R2 and R3 differ on purpose:**
  - **Step entry:** R2 is driven by the coordinator; R3 has one entry with a callback. The reason is R3's run-scoped gateway and breaker.
  - **Execution:** R2 and R3 both run in the background (R2-C6 Iteration 2, R3-C7). R2 takes seconds and R3 minutes, so R2's stale cutoff is shorter (10 vs 30 min).
  - **Serialization:** R3 needs tuple-key encoding.
  - **Instances:** R3 needs one instance per run.
  - **Provider limits:** R2 shares one Places cap; R3 shares one limit per web provider (Parallel search slots, Firecrawl slots + rate limiter), each behind the run's own limit.
  - **Step table:** R3's has a `degraded` status for a breaker-open STEP 3; R2 has no degraded step.
  - **Status from memory:** R3's memory reply carries `completed_step` (its progress screen needs it); R2's doesn't.
  - **Config errors:** R2 checks Google's cause chain in discovery and enrichment; R3 can only check at gateway open (the LLM case stays open).
- **Unchanged:** every step method body, every state object's fields and types, every degradation and edge-case rule, and `DeepSearch` (it calls R1 only).
- **Prerequisites found in the code,** not in the problem statement:
  - the gateway shared across runs (R3-C2);
  - the tuple keys that can't round-trip (R3-C4);
  - the breaker-degraded STEP 3 (R3-C3);
  - the per-gateway provider limits that multiply with parallel runs (R3-C2 Iteration 1);
  - a refused key that looks like a transient failure (R3-C7 Iteration 1);
  - origin and radius missing from R1's output (R2 flow, step 1).
- **Left out on purpose:**
  - a cap on concurrent R3 runs (R3-C2 Iteration 1 limits each provider instead);
  - an app-wide cap on LLM calls (R3-C2 Iteration 1);
  - a Places retention policy (R2-C4: data is kept for now; the policy comes in a later phase);
  - deduplicating repeated starts;
  - per-item checkpoints inside a step (the whole step is the unit);
  - automatic retries;
  - STEP 6.

## Sources Consulted

- Durable-workflow checkpoint patterns on Postgres (a per-step output table, idempotent checkpoints, claim-by-conditional-update): [InfoQ: Durable workflows on Postgres](https://infoq.com/articles/durable-workflows-postgres), [DBOS: Postgres transactions](https://www.dbos.dev/blog/co-locating-workflow-state-with-your-data), [dev.to: what you don't need Temporal for](https://dev.to/contrite42/durable-workflows-on-postgres-what-you-dont-need-temporal-actually-buys-you-3o0f).
- Google Maps Platform caching terms (lat/lng up to 30 days; place IDs under the Places API Policies): [Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms/index-20240522).
- Pydantic `TypeAdapter`: [API reference](https://pydantic.dev/docs/validation/2.7/api/pydantic/type_adapter/). The tuple-key behavior was confirmed with a local scratch test, not from the docs.
