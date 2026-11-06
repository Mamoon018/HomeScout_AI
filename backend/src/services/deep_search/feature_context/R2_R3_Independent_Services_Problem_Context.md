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
- **Never save a degraded step:** a step whose output was degraded by an outage, rather than by real data, is not saved. Saving it would make the outage permanent on retry (see R3-C3).

## Two Facts the Code Showed (corrections to the Problem Context)

- **R2's input is not only R1's output.** R1's finished output gives `category_metric_plans`. The search **origin** (`GeoPoint`) and **radius** are not part of R1's output, so the R2 start request has to supply them. `radius_km` falls back to `DEFAULT_RADIUS_KM` (2.0).
- **R2 is short and R3 is long.** R2 asks for at most `DISCOVERY_MAX_RESULTS = 10` places per category, then runs one routing re-search per category per mode (walk, drive, cycle) and one transit matrix per 100 places, all concurrently, so it takes seconds. R3 runs LLM turns and web searches for every amenity, so it takes minutes. "Runs take minutes" holds for R3 only, and this changes the execution-model choice between them (R2-C6 vs R3-C7).

---

# R2. Amenity Search — Feature Process Flow

R2 takes a finished R1 run plus a search origin, and produces one `PredefinedMetricsRecord` per discovered place per category. It needs **8 components**. R2's three step methods are reused exactly as they are.

## R2 Runtime Flow

1. The customer (or the page, after R1 finishes) sends `POST /api/amenity-search/runs` with `r1_run_id`, `origin` and an optional `radius_km`.
2. The login check verifies the user. The request model checks that `origin` is a finite coordinate and `radius_km` is positive, and rejects bad input with `422` before any row exists.
3. The coordinator reads R1's **finished** output through `R1RunStore.get_finished_output(r1_run_id, user_id)`. A missing run gives `404`, and a run that is not finished gives `409`.
4. The coordinator builds `AmenitySearchState(origin, radius_km, category_metric_plans)` and creates the `r2_runs` row with status `running`, `attempts = 0`, `completed_step = null` and this initial state saved.
5. **Step `discovery`** (M1.1, `run_place_discovery`) runs. When it completes, the state is saved as a checkpoint, `completed_step = "discovery"`.
6. **Step `enrichment`** (M1.2, `run_accessibility_enrichment`) runs. No save follows, because the next step has no I/O (see the persistence rule).
7. **Step `attachment`** (M1.3, `run_result_attachment`) runs in memory.
8. The **finish write** saves the final state and the output (`category_metric_plans`, `discovered_places`, `predefined_records`) and sets `finished`. The response is `201` with `result`.
9. **On any failure,** the run is saved as `failed` with its stage, message and `retryable` flag. The saved state and `completed_step` are left untouched.
10. **Retry:** `POST /api/amenity-search/runs/{run_id}/retry` (no body).
    - The store claims the run in **one conditional update**: it must be `failed` and retryable, or `running` and stale. On success it becomes `running` with `attempts + 1`.
    - A losing request gets `409`.
    - The coordinator loads the saved state and resumes at the **first step after `completed_step`**.
11. **Status:** `GET /api/amenity-search/runs/{run_id}` returns `status`, `completed_step`, and `result` or `retryable`. It is read-only.
12. **R3** reads the finished output by `run_id` and `user_id` (R2-C4 "Get the finished output").

## What Already Exists and Is Reused As-Is

| Built-in | Where | Used for |
|---|---|---|
| M1.1 / M1.2 / M1.3 step methods | `AmenitySearch.run_place_discovery`, `run_accessibility_enrichment`, `run_result_attachment` | Every step that produces a value |
| R2's typed errors, each with a `stage` | `PlaceDiscoveryError`, `AccessibilityEnrichmentError`, `ResultAttachmentError` in `src/exceptions/deep_search.py` | Failure stage and the retryable split |
| R1 finished-output read | `R1RunStore.get_finished_output` | R2's input |
| R1 HTTP pattern: coordinator, store, controller, routes, `get_authenticated_user`, `user_id` filter, `RunConflictError` / `RunNotFoundError` / `RunStoreError`, `retryable` in every failed body | `r1_run_coordinator.py`, `r1_run_store.py`, `app/api/...` | The shape every R2 piece copies |
| Async service-role Supabase client, migrations folder | `create_supabase_db_client`, `backend/supabase/migrations/` | The `r2_runs` table |
| `create_amenity_search` factory | `amenity_search.py` | Building R2 once at app startup |

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
- **No run-scoped resources:** R2 holds no session or breaker that has to live across steps. The Places/Routes clients are long-lived and shared.
- **Exact resume position:** a step's output being empty is a valid result (a category can have zero places).

### Reasoning
- **Approach 3** breaks on valid empty outputs. A discovery that found nothing would be repeated on every resume, so it fails *exact resume position*.
- **Approach 2** is right when steps share run-scoped resources (as in R3), but R2 has none. Adding the entry would mean new service code with nothing to gain.
- **Approach 1** needs no change to `AmenitySearch` at all, keeps knowledge of persistence out of the service, and the coordinator can test the plan directly.

### Critical Decision Choices
- **General — where the step list lives:** in the R2 coordinator, as a module-level ordered tuple, so the resume rule and the step order can't drift apart.
- **Context-specific — enrichment checkpoint:** left out on purpose, by rule 2 of the persistence rule. **Risk accepted:** a hard crash in the moment between enrichment ending and the finish write would repeat enrichment on retry.
- **Context-specific — the empty-place shortcut:** `run_accessibility_enrichment` returns early when no place has a location. This is unchanged, and the plan treats it as a completed step.

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

### Three Common Approaches
1. **One row per run: the whole state as one versioned jsonb, plus a `completed_step` column. (Finalized)** Each checkpoint rewrites `state`.
2. **A run row plus a step-output table** `r2_run_steps(run_id, step, output jsonb, primary key (run_id, step))`. Each step's own output is inserted once, and a resume rebuilds the state from the rows. This is the durable-workflow "operation outputs" pattern.
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
- **Approach 2** recovers from crashes, still stops overlapping retries (a live run is never stale), and needs one timestamp comparison in the update R1 already has. Fencing covers the rare case where a run is slower than `stale_after`. A clean shutdown doesn't even wait, because the coordinator saves the run as failed and retryable on cancellation (R2-C6).

### Critical Decision Choices
- **General — whose clock:** `updated_at` is set by the database trigger. The stale cutoff is computed in the backend and passed as a filter. A small clock skew only shifts the wait slightly. The value must be much longer than the skew.
- **Context-specific — `stale_after` for R2:** **10 minutes**, as a setting. R2's longest step takes seconds, so this is very generous.
- **Context-specific — what a lost fence does:** the old execution logs `r2_run.superseded`, makes no further writes, and returns `409` if it is still attached to a request.

---

## R2-C6. R2 Run Coordinator

### Goal of Component
One service runs R2's step plan around the store. Start: check inputs → load R1 output → create the row → run the steps → checkpoint → finish. Retry: claim → load → resume after `completed_step` → finish. Any R2 error saves the run as failed with its stage and `retryable` flag.

### Problem It Aims to Solve
C2 knows the steps and C4/C5 know the database, but nothing applies the status, retry and fencing rules. In the HTTP layer they couldn't be tested without a server.

**Traces to:** "started, tracked and retried … on its own", "retried from the first unfinished step", "tell retryable failures from non-retryable ones".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **The run ID** is created once at start and set on `run_id_var`, so every log line carries it, as in R1.
- **The retryable split:**

  | Error | Retryable | Why |
  |---|---|---|
  | `PlaceDiscoveryCallError`, `RoutingRetrievalError`, `TransitRetrievalError` | Yes, while `attempts < MAX_RETRY_ATTEMPTS` | Provider failure; a second call may succeed |
  | `PlaceDiscoveryRequestError` | No | Bad input (empty taxonomy node, no `places.*` targets); it fails again |
  | `ResultAssemblyError` | No | The plans and the places don't match; it fails again |
  | `StateVersionMismatchError` | No | Start again (R2-C3) |
  | Any other exception | No, stage `unexpected` | A bug |
  | Cancellation (shutdown, client gone) | Yes | Best-effort save as failed, then re-raise |

- `R2_STAGE_ERRORS` / `R2_PROVIDER_ERRORS` tuples next to R1's, with `502` vs `503` mapped as R1 does.
- An `R2RunFailedError` that carries `run_id`, `stage`, `retryable` and `provider_unavailable`, mirroring `R1RunFailedError`.
- "Save as failed quietly": if the store is down too, log it and keep the R2 error as the answer, as in R1.

### Three Common Approaches
1. **Run inside the request. (Finalized for R2)** As R1 does: the start or retry request waits until R2 finishes or fails and gets the result in the response.
2. **`202 Accepted` + in-process background task + status polling.**
3. **An external job queue and worker** (for example arq with Redis): the request queues a job and a worker process runs it.

### Critical Factors (from our context)
- **Run length:** R2 takes seconds, not minutes (see the corrections above).
- **Consistency with R1:** the same request/response model for the page.
- **Proportionate simplicity:** no new infrastructure exists (no Redis or worker).
- **Crash recovery** is already handled by R2-C5, whichever model is used.

### Reasoning
- **Approach 3** survives process loss best and scales out, but it brings new infrastructure and a deployment unit for a step that takes seconds.
- **Approach 2** is right for runs that outlast proxy and browser timeouts (R3-C7). For R2 it would only add polling to the page for no benefit.
- **Approach 1** fits a seconds-long run, matches R1, and loses nothing: if the connection drops, the handler either finishes and saves (and the page reads it with `GET`), or it is cancelled and saved as retryable.

### Critical Decision Choices
- **General — what the response carries:** `result` = `predefined_records` (what the page shows), plus `run_id`, `status` and `completed_step`.
- **Context-specific — the R1 run must be the same user's and `finished`:** `get_finished_output` already filters on both, and returns nothing otherwise. The coordinator then loads the R1 row to tell apart `404` (no such run for this user) and `409` (not finished).
- **Context-specific — whether a client disconnect cancels the handler:** `log_requests` is an `http` middleware, so this must be confirmed in verification. Either way the result is safe: the run is saved, or it is saved as failed and retryable.
- **Context-specific — two R2 runs for the same R1 run:** allowed. Each is its own run, since starting twice is a deliberate customer action and not a retry. Not deduplicated (not in the problem statement).

---

## R2-C7. R2 HTTP Endpoints

### Goal of Component
The page reaches R2-C6 over HTTPS with start, retry and status, behind the login check, with R1's status codes and body shapes.

### Problem It Aims to Solve
No R2 routes exist, and app startup doesn't build R2 or its store.

**Traces to:** "started, tracked and retried for a specific user", "behave like R1 in how they are started, report status … and handle retries".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **Startup:** at app startup (`lifespan`), build `AmenitySearch` (`create_amenity_search`, with the shared LLM caller injected), `R2RunStore` and the coordinator once. Close the Places/Routes clients on shutdown, and set `app.state.r2_run_coordinator = None` when the service-role key is missing (giving `503`, as R1 does).
- **Layers:** a dependency `get_r2_run_coordinator`, a routes file of declarations only, and a controllers file that maps typed errors to codes, copying R1's split.
- **Models:** `StartAmenitySearchRequest { r1_run_id: UUID, origin: {latitude, longitude}, radius_km?: float > 0 }`, plus a response that adds `completed_step`.
- **Bodies:** every failed body carries `retryable`.
- **Wiring:** register the router and add a Swagger tag.

### Three Common Approaches
1. **Separate action endpoints under `/api/amenity-search/runs`, mirroring R1. (Finalized)**

   | Purpose | Method and path | Success | Errors |
   |---|---|---|---|
   | Start | `POST /api/amenity-search/runs` | `201` + `result` | `422` bad origin/radius; `404` R1 run not found; `409` R1 not finished; `502`/`503` R2 failed (`retryable`); `500` unexpected |
   | Retry | `POST /api/amenity-search/runs/{run_id}/retry` (no body) | `200` + `result` | `404`; `409` not failed/not retryable/claim lost/stale not yet; `502`/`503`/`500` |
   | Status | `GET /api/amenity-search/runs/{run_id}` | `200` + `status`, `completed_step`, `result` or `retryable` | `404`; `503` store down |
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
- **Context-specific — refresh recovery:** the page stores `run_id` in `sessionStorage` and calls `GET`, as with R1.

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
| Round trip | The initial, after-discovery and finished states, and the output, come back equal, including real `Place.to_dict` data. |
| Version mismatch | Rejected as failed, not retryable. |
| Concurrent retries | Two retries sent at the same time: exactly one runs, the other gets `409`. |
| Stale reclaim | A `running` row older than `stale_after` can be claimed; a fresh one can't. |
| Fencing | A write made with an old `attempts` changes nothing. |
| Retry limit | After one retry, a second failure is saved with `retryable: false`. |
| Retryable split | Each error in the R2-C6 table gives the listed `retryable`. |
| Ownership | Every read and write for another user's run finds nothing; RLS blocks the publishable key. |
| Migration | Re-running it changes nothing. |
| HTTP | Each status code in R2-C7, including `401` without the cookie. |
| Regression | The existing R2 tests and sample runs pass after the state split. |

### Three Common Approaches
1. **Real providers and the real dev Supabase, with record/replay of provider responses, in `backend/tests_live/`. (Finalized)** R1's method, extended to the Places/Routes clients.
2. **Fakes for the providers and the store, in `tests/` only.**
3. **Contract tests at the HTTP layer only.**

### Critical Factors (from our context)
- **The output can't be reproduced** live, so parity needs replay.
- **The guard is a database behavior:** the conditional update and the trigger can only be proven on Postgres.
- **Consistency with R1's C6.**

### Reasoning
- **Approach 2** can't prove the conditional update, the trigger, RLS or the migration.
- **Approach 3** can't show *which* step reran.
- **Approach 1** proves both the database rules and parity, and the replay keeps parity exact.

### Critical Decision Choices
- **General — cost and time:** live runs make paid Places/Routes calls. The replayed paths make none.
- **Context-specific — call counting:** the recording wrapper also counts calls per step, which is the evidence for "discovery runs once".

---

# R3. Specific Metric Resolution — Feature Process Flow

R3 takes a finished R2 run. For each discovered place whose category has `specific_metrics`, it finds the place's website, searches for evidence and resolves each metric. It needs **9 components**. R3's STEP 1–5 logic is reused exactly as it is. The only change inside the service is a resume point and a save hook in its one entry method (R3-C3).

## R3 Runtime Flow

1. The page sends `POST /api/specific-metric-resolution/runs` with `r2_run_id`.
2. The login check verifies the user. The coordinator reads R2's **finished** output through `R2RunStore.get_finished_output(r2_run_id, user_id)`. A missing run gives `404`, and a run that is not finished gives `409`.
3. The coordinator builds `SpecificMetricResolutionState(category_metric_plans, discovered_places, predefined_records)` from that output and creates the `r3_runs` row with `running`, `attempts = 0`, `completed_step = null` and this initial state saved.
4. The response is **`202 Accepted`** with `run_id` and `status: running`. The run continues in a background task (R3-C7).
5. The background task builds a **fresh R3 instance with its own tool gateway** (R3-C2) and calls `run_specific_metric_resolution(state, resume_after=None, on_step_completed=…)`.
6. Inside the method, unchanged: open the gateway, then **STEP 1** (plan index) and **STEP 2** (work items), which are cheap and always recomputed, then build the phase-1 catalog.
7. **STEP 3** (discovery batch: official-URL gate + website discovery). At its barrier the method awaits `on_step_completed("discovery_batch", state, breaker_open)`. The coordinator saves a checkpoint (`completed_step = "discovery_batch"`) **only if the breaker is closed** (R3-C3).
8. **STEP 4** (one pipeline per amenity: phase-1 search loop + resolution turn) and **STEP 5** (sweep into `resolution_results` + the run-level raise) run unchanged.
9. The gateway closes (unchanged `finally`). The **finish write** saves the final state and output (`resolution_results`) and sets `finished`.
10. **On any failure,** the run is saved as `failed` with its stage, message and `retryable` flag. `state` and `completed_step` are left untouched.
11. **Retry:** `POST /api/specific-metric-resolution/runs/{run_id}/retry` (no body).
    - The store claims the run in **one conditional update**: it must be `failed` and retryable, or `running` and stale. A losing request gets `409`.
    - On success the response is `202`. The background task resumes with `resume_after = completed_step`: STEP 1/2 are recomputed, STEP 3 is **skipped** if it was saved, and STEP 4 runs.
12. **Status:** `GET /api/specific-metric-resolution/runs/{run_id}` returns `status`, `completed_step`, and `result` or `retryable`. The page polls it while the run is `running`.

## What Already Exists and Is Reused As-Is

| Built-in | Where | Used for |
|---|---|---|
| STEP 1–5 logic: plan index, work items, catalog, discovery batch, pipelines, sweep, run-level raise, circuit breaker | `SpecificMetricResolution` | Every value R3 produces |
| R3's typed errors | `MetricResolutionProviderError` (with `cause`), `MetricResolutionValidationError`, `McpConnectionError`, `McpToolUnavailableError` | Failure stage and the retryable split |
| `create_specific_metric_resolution` factory | `specific_metric_resolution.py` | Building one R3 instance per run (R3-C2) |
| R2 finished-output read | `R2RunStore.get_finished_output` (R2-C4) | R3's input |
| The guard, store layout and HTTP pattern | R2-C4, R2-C5, R2-C7 (and R1) | Copied with R3's own table and settings |

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
- **Context-specific — rate limits are per gateway:** the Firecrawl token bucket and the search semaphores are per instance. With one instance per run, two parallel runs can make twice the calls on the same provider account. **Accepted for now** (few customers). A process-wide cap on active R3 runs is noted as a follow-up, not built.
- **General — where the factory lives:** in `app.state`, built at startup from settings.

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

- **The degraded-step rule:** when the breaker is open at the end of STEP 3, every remaining amenity got `WebsiteSearchResult(None, "none")` because of the outage, not because no website exists. Saving that would make every retry run STEP 4 without websites. So STEP 3 is **not** saved when `breaker_open` is true, and a retry reruns it.
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
- **Context-specific — the internal `run_id = uuid4().hex` in STEP 4:** kept as it is. Log lines are tied to the HTTP run through `run_id_var`, set by the coordinator as in R1.
- **Context-specific — no work items:** STEP 3 runs on an empty list and is saved, STEP 4 is skipped (the catalog is `None`), and the run finishes with empty results. This is unchanged behavior.

---

## R3-C4. R3 State Serialization (Tuple Keys)

### Goal of Component
A saved R3 state turns into JSON and back with nothing lost, including the four dicts keyed by `(category_id, place_id)`.

### Problem It Aims to Solve
`website_search_results`, `discovery_search_results`, `official_gate_results` and `resolution_results` are `dict[tuple[int, str], …]`. **Tested in a scratch script (Pydantic 2.13):** R1's `TypeAdapter` method dumps the key `(1, "a,b")` as the string `"1,a,b"`, and loading it back **fails** (`Input should be a valid tuple`). Joining the parts with a comma isn't safe either, because place IDs are opaque strings.

**Traces to:** "the saved results it builds on must load back unchanged."

### Mandatory Sub-Tasks Independent of Approaches Taken
- Round-trip tests for the initial, after-STEP-3 and finished states, including keys whose `place_id` contains `,`.
- A version envelope with `R3_STATE_SCHEMA_VERSION`. A mismatch means failed, not retryable.

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
- `R3RunStore` in `r3_run_store.py` with R2-C4's seven operations, the `user_id` filter on every query, and the fencing filter on every write after the claim.
- "Save as failed" never touches `state` or `completed_step`.

### Three Common Approaches
Same three as R2-C4: **(1) one row with the versioned state blob + `completed_step` (Finalized)**, (2) a run row + a step-output table, (3) a column per step output.

### Critical Factors (from our context)
- **One mid-run checkpoint** (STEP 3) plus the finish write.
- **R3's state is the largest one,** because it carries R2's places and records plus evidence, so each rewrite is bigger.
- **Consistency with R1 and R2.**

### Reasoning
State size is the only factor that could favor Approach 2 (write only the step's own output). With two writes per run, rewriting the whole state twice is still cheap, and Approach 1 keeps R3 identical to R1 and R2.

### Critical Decision Choices
- **Context-specific — what `output` holds:** `resolution_results` (encoded as in R3-C4) while STEP 6 is unbuilt. When STEP 6 lands, the output switches to `amenity_records`, with a version bump.
- **Context-specific — Places content:** R3's state carries `predefined_records` (Places content), so the retention decision in R2-C4 applies here too: kept for now, with the policy decided in a later phase.

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
- **Context-specific — `stale_after` for R3:** **30 minutes**, as a setting. It must be longer than the longest STEP 4 seen in live runs; the verification records STEP 4 durations to check this.

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

  | Error | Retryable | Why |
  |---|---|---|
  | `MetricResolutionProviderError` at run level (`cause`: `availability`, `circuit_open`, `content`) | Yes, while `attempts < MAX_RETRY_ATTEMPTS` | Provider failure; later calls may succeed |
  | `McpConnectionError` (gateway can't connect) | Yes | Transient |
  | `MetricResolutionValidationError` (catalog can't be built) | No | The gateway schema doesn't match; it fails again |
  | `McpToolUnavailableError` (a required tool is missing) | No | Configuration; it fails again |
  | `StateVersionMismatchError` | No | Start again |
  | `RunSupersededError` (lost fence) | Not saved | A newer execution owns the row |
  | Any other exception | No, stage `unexpected` | A bug |
  | Cancellation (shutdown) | Yes | Best-effort save as failed, then re-raise |

- `R3_STAGE_ERRORS` / `R3_PROVIDER_ERRORS` tuples and an `R3RunFailedError` mirroring R1's, so the status endpoint can say `503`- vs `502`-style causes in the log.
- `run_id_var` is set inside the background task, so every R3 log line carries the HTTP run ID.
- The per-run R3 instance (R3-C2) is closed in the task's `finally`.

### Three Common Approaches
1. **Run inside the request,** as R1 and R2 do.
2. **`202 Accepted` + an in-process background task (`asyncio.create_task`) + status polling. (Finalized for R3)**
3. **An external job queue and worker** (arq/Redis, or Celery).

### Critical Factors (from our context)
- **Run length is minutes** (Environment b: "requests time out").
- **Crash recovery** is already handled by R3-C6.
- **Proportionate simplicity:** no queue infrastructure exists.
- **Consistency with R1** in endpoints, store and error bodies, if not in timing.

### Reasoning
- **Approach 1** is right for R1 and R2 (seconds), but for R3 it turns normal runs into client timeouts.
- **Approach 3** gives the strongest isolation, but its main benefit, surviving process loss, is already covered by the stale reclaim and the step checkpoint, and it adds Redis and a worker deployment.
- **Approach 2** needs only the status endpoint R1 already has, and fits the existing single FastAPI process.

### Critical Decision Choices
- **General — keeping tasks alive:** tasks are held in a set on `app.state`, so they aren't garbage-collected, and removed when done.
- **General — shutdown:** `lifespan` cancels the running tasks and awaits them (with a short timeout). Each task saves its run as failed and retryable on `CancelledError`.
- **Context-specific — the input must be the same user's finished R2 run:** checked before the row is created, so a bad `r2_run_id` gets `404`/`409` and no run is created.
- **Context-specific — this departs from R1:** the start and retry responses are `202` with `status: running`, not a result. The page polls `GET` (or uses refresh recovery) to see the result.

---

## R3-C8. R3 HTTP Endpoints

### Goal of Component
The page starts, retries and polls R3 over HTTPS behind the login check, with R1's body shapes.

### Problem It Aims to Solve
No R3 routes exist, and app startup doesn't build R3's factory, store, coordinator or task set.

**Traces to:** "started, tracked and retried for a specific user", "behave like R1 in how they … report status … and handle retries".

### Mandatory Sub-Tasks Independent of Approaches Taken
- **Startup:** at app startup (`lifespan`), build the R3 factory (with the shared caller), `R3RunStore`, the coordinator and the task set. Cancel and await the tasks on shutdown. With no service-role key, give `503`, as R1 does.
- **Layers:** a dependency, routes and controllers split, as in R1.
- **Models:** `StartSpecificMetricResolutionRequest { r2_run_id: UUID }`, and a response with `run_id`, `status`, `completed_step`, `result` and `retryable`.
- **Wiring:** register the router and add a Swagger tag.

### Three Common Approaches
1. **Separate action endpoints under `/api/specific-metric-resolution/runs`, mirroring R1. (Finalized)**

   | Purpose | Method and path | Success | Errors |
   |---|---|---|---|
   | Start | `POST /api/specific-metric-resolution/runs` | `202` + `run_id`, `status: running` | `404` R2 run not found; `409` R2 not finished; `503` store down |
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
Evidence that R3's output is unchanged, that the resume skips a saved STEP 3, that a degraded STEP 3 is not saved, and that the guard holds under background execution.

### Problem It Aims to Solve
R3 is the costliest and least reproducible service, so a wrong resume point or a lost fence costs money and silently changes results.

**Traces to:** "without changing what either service computes", "must not repeat finished steps", "only one request at a time", "load back unchanged".

### Mandatory Sub-Tasks Independent of Approaches Taken
| Test | Passes when |
|---|---|
| Default parity | Calling `run_specific_metric_resolution(state)` with no new arguments gives the same result as before the change. The existing R3 suites pass unchanged, apart from the state class. |
| Resume parity | A failure injected in STEP 4, then a retry, gives the same final state as a run that never failed, with the same replayed provider responses. **STEP 3 provider calls are made once in total.** |
| Degraded STEP 3 not saved | With the breaker forced open during STEP 3, no checkpoint is written, and a retry reruns STEP 3. |
| Breaker on resume | A resumed run starts with a closed breaker. |
| Tuple-key round trip | The four keyed dicts come back equal, including a `place_id` containing `,`, in the same order. |
| Per-run instance | Two R3 runs at the same time: one finishing doesn't close the other's gateway. |
| Background lifecycle | Start returns `202` before STEP 1. A shutdown mid-run saves `failed` + `retryable`. The task set is empty after completion. |
| Concurrent retries / stale reclaim / fencing / retry limit | As in R2-C8, against `r3_runs`. |
| Retryable split | Each error in the R3-C7 table gives the listed `retryable`. |
| Ownership, RLS, migration, HTTP codes | As in R2-C8, for R3's table and endpoints. |
| STEP 4 duration | Recorded on live runs, to confirm `stale_after` (R3-C6). |

### Three Common Approaches
Same three as R2-C8: **(1) real providers + dev Supabase with record/replay (Finalized)**, (2) fakes only, (3) HTTP contract tests only.

### Critical Factors (from our context)
- **LLM and web output vary per call,** so parity needs replay.
- **A live STEP 4 is expensive,** so the tests must keep live runs to a few amenities.

### Reasoning
As R2-C8. R3 adds one more reason: only live runs show real STEP 4 durations, and those set `stale_after`.

### Critical Decision Choices
- **Context-specific — keep live runs small:** use one or two categories with specific metrics and three places each, so a live run stays within a few minutes and a small token budget.
- **General — fakes stay for logic:** the existing fake-gateway suites (`test_r3_m1_3_*`, `test_r3_m1_4_*`, `test_r3_m2_2_*`) keep covering the decision logic. The live tests only cover what fakes can't (the database, the guard, real durations).

---

# Review Check (R2 and R3)

- **Order:**
  - **R2:** C1 → C2 and C3; C3 → C4 → C5; C2 + C5 → C6 → C7; C8 covers all.
  - **R3:** R2-C1 → R3-C1 → C3 and C4; C4 → C5 → C6; C2 + C3 + C6 → C7 → C8; C9 covers all.
  - No component is unconnected.
- **Approaches are real alternatives:** each one listed would meet its component's goal on its own. Mandatory work (fencing, `user_id` filters, version envelopes, round-trip tests) sits under Mandatory Sub-Tasks, not among the approaches.
- **Where R2 and R3 differ on purpose:**
  - **Step entry:** R2 is driven by the coordinator; R3 has one entry with a callback. The reason is R3's run-scoped gateway and breaker.
  - **Execution:** R2 runs inside the request (seconds); R3 runs in the background (minutes).
  - **Serialization:** R3 needs tuple-key encoding.
  - **Instances:** R3 needs one instance per run.
- **Unchanged:** every step method body, every state object's fields and types, every degradation and edge-case rule, and `DeepSearch` (it calls R1 only).
- **Prerequisites found in the code,** not in the problem statement:
  - the gateway shared across runs (R3-C2);
  - the tuple keys that can't round-trip (R3-C4);
  - the breaker-degraded STEP 3 (R3-C3);
  - origin and radius missing from R1's output (R2 flow, step 1).
- **Left out on purpose:**
  - a cap on concurrent R3 runs (R3-C2);
  - a Places retention policy (R2-C4: data is kept for now; the policy comes in a later phase);
  - deduplicating repeated starts;
  - per-item checkpoints inside a step (the whole step is the unit);
  - automatic retries;
  - STEP 6.

## Sources Consulted

- Durable-workflow checkpoint patterns on Postgres (a per-step output table, idempotent checkpoints, claim-by-conditional-update): [InfoQ: Durable workflows on Postgres](https://infoq.com/articles/durable-workflows-postgres), [DBOS: Postgres transactions](https://www.dbos.dev/blog/co-locating-workflow-state-with-your-data), [dev.to: what you don't need Temporal for](https://dev.to/contrite42/durable-workflows-on-postgres-what-you-dont-need-temporal-actually-buys-you-3o0f).
- Google Maps Platform caching terms (lat/lng up to 30 days; place IDs under the Places API Policies): [Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms/index-20240522).
- Pydantic `TypeAdapter`: [API reference](https://pydantic.dev/docs/validation/2.7/api/pydantic/type_adapter/). The tuple-key behavior was confirmed with a local scratch test, not from the docs.
