# R2 Amenity Search as an Independent Service: Implementation Plan

## Context

R2 (Amenity Search) runs today only in-process, through one shared `AmenitySearchState` that also carries R3's fields. Nothing starts, tracks or retries R2 on its own, and a failure throws away paid Places/Routes results that can't be reproduced. [R2_R3_Independent_Services_Problem_Context.md](backend/src/services/deep_search/feature_context/R2_R3_Independent_Services_Problem_Context.md) (R2-P1, R2-C1 to R2-C8) and Part A of [R2_R3_HTTP_Traceflow.md](backend/src/services/deep_search/feature_context/R2_R3_HTTP_Traceflow.md) define the fix. This plan builds it.

**What gets built:**
- R1 writes its finished output to a new `r1_runs.output` column (R2-P1), so R2 reads its input in one read.
- R2 state split from R3 (R2-C1); R3's fields move unchanged to `SpecificMetricResolutionState`.
- `r2_runs` + `r2_run_steps` tables, a store, a versioned state codec (R2-C3, R2-C4).
- A coordinator that runs R2's three existing step methods in a background task, checkpoints after discovery, fences every write on `attempts`, claims retries atomically (failed+retryable, or running+stale), and splits retryable from non-retryable failures, including the Google config-error check (R2-C2, R2-C5, R2-C6).
- Per-run `AmenitySearch` with a per-run Places limit of 3 under a global cap of 15 (R2-C2 Iteration 1).
- Three endpoints under `/api/amenity-search/runs`: start `202`, retry `202`, status `200` with an in-memory live-task check (R2-C7).
- Fake-based tests (R2-C8) and a live sample runner.

**What does not change:** discovery, enrichment and attachment logic, and every object they produce. Given the same Places/Routes responses, R2's output is identical.

**Decisions taken in this plan (beyond the spec):**
- **D-R2-1, `r1_runs.output` CHECK is added `NOT VALID`.** R2-P1 asks for `(status = 'finished') = (output is not null)`, but R1 runs finished before the column exist with `output = null`, so a validated CHECK would fail to apply. `NOT VALID` enforces it on every new write and leaves old rows (terminal, never updated again) alone. They read as `404` for R2, as the spec says.
- **D-R2-2, R1's status endpoint keeps its replay.** R2-P1 mentions R1's E3 reading `output` as "agreed but a separate change". It is outside R2's scope and would need a second path for pre-column rows, so it is not built here.
- **D-R2-3, a database error inside a run is retryable** (your answer). `RunStoreError` on the checkpoint or finish write is saved with stage `run_store` and `retryable = attempts < 1`, matching traceflow A10.
- **D-R2-4, the sample runner seeds the real M1.1 capture** (your answer), so live enrichment joins real places.
- **D-R2-5, `R2RunFailedError` is not built.** Since Iteration 2, failures never reach a controller; they are saved on the row and read through status. Nothing would catch it.

On accept, this plan is also saved as `backend/src/services/deep_search/feature_context/R2_Independent_Service_Implementation_Plan.md` (not a build todo).

---

## Build checklist (todos, in order)

1. Migration `backend/supabase/migrations/20261108000000_add_r1_runs_output.sql`: `output jsonb`, CHECK `NOT VALID` (D-R2-1).
2. R1 store and coordinator (R2-P1): `R1RunStore.mark_finished` (status + output in one fenced UPDATE), `R1RunStore.get_finished_output`, output codec; `R1RunCoordinator._settle` uses `mark_finished`. Update R1's `FakeRunStore` (tests) and the R1 step-persistence sample runner's row holder with `mark_finished`.
3. Migrations `20261108000100_create_r2_runs.sql` and `20261108000200_create_r2_run_steps.sql` (R2-C4, R2-C4 Iteration 1).
4. Contracts in `feature_schemas/schemas.py`: slim `AmenitySearchState`; new `SpecificMetricResolutionState`, `AmenitySearchOutput`, `R2RunStatus`, `R2StepName`, `R2StepId`, `R2StepRecord`, `R2RunRecord`, `R2RunView`.
5. R3 annotation switch: `specific_metric_resolution.py` types against `SpecificMetricResolutionState` (no body change); update the 5 R3 feature tests and the `R3.M1.4_url_discovery_and_web_search.py` runner to build the R3 state; update `tests/.../test_result_attachment.py` (drop the `amenity_records` assert).
6. `AmenitySearch`: optional `global_places_semaphore` and `owns_clients` keywords; Places calls take run slot then global slot; `GLOBAL_PLACES_CONCURRENCY = 15`.
7. Exceptions: `R2_STAGE_ERRORS`, `R2_PROVIDER_ERRORS` tuples in `src/exceptions/deep_search.py`; widen the `RunStoreError` docstring to cover `r2_runs`.
8. Setting `r2_stale_after_seconds` (default 600) in `src/core/config.py` (and `.env.example` if present).
9. New `r2_run_store.py`: state/output/step codecs + run-row and step-row operations.
10. New `r2_run_coordinator.py`: step plan, start/retry/status, background task set, execute, checkpoint/finish/fail, config-error check, shutdown.
11. HTTP: `src/schemas/amenity_search.py` (request/response models), `src/app/api/controllers/amenity_search.py`, `src/app/api/routes/amenity_search.py`, `get_r2_run_coordinator` in `dependencies/deep_search.py`, wiring + Swagger tag + shutdown order in `src/app/main.py`.
12. New tests `tests/services/deep_search/test_r2_run_lifecycle.py` (fakes only, R2-C8 table) plus an R2-P1 block in `test_r1_pause_resume.py`.
13. New live sample runner `feature_sample_runs/r2_run_lifecycle_sample_run.py`.
14. Run `pytest tests src/services/deep_search/feature_tests` and compare with the saved baseline (37 pre-existing failures, none new); run the sample runner. Fix whatever fails.

---

## 1. File and Module Structure

| File | Change | Owns |
|---|---|---|
| `backend/supabase/migrations/20261108000000_add_r1_runs_output.sql` | new | `r1_runs.output`, CHECK `r1_runs_output_iff_finished` `NOT VALID` |
| `backend/supabase/migrations/20261108000100_create_r2_runs.sql` | new | `r2_runs` DDL, `user_id` index, RLS on, `updated_at` trigger |
| `backend/supabase/migrations/20261108000200_create_r2_run_steps.sql` | new | `r2_run_steps` DDL, checks, completed-immutable trigger |
| `backend/src/services/deep_search/feature_schemas/schemas.py` | modify | R2/R3 state split + R2 run contracts |
| `backend/src/services/deep_search/specific_metric_resolution.py` | modify | annotations only (`SpecificMetricResolutionState`) |
| `backend/src/services/deep_search/amenity_search.py` | modify | two constructor keywords, slot order, `aclose` ownership; no logic change |
| `backend/src/services/deep_search/r1_run_store.py` | modify | `mark_finished`, `get_finished_output`, R1 output codec |
| `backend/src/services/deep_search/r1_run_coordinator.py` | modify | `_settle` finishes through `mark_finished` |
| `backend/src/services/deep_search/r2_run_store.py` | new | the only R2 module that knows Supabase: codecs + row operations |
| `backend/src/services/deep_search/r2_run_coordinator.py` | new | R2 run lifecycle: step plan, guard, background tasks, retryable split |
| `backend/src/exceptions/deep_search.py` | modify | `R2_STAGE_ERRORS`, `R2_PROVIDER_ERRORS` |
| `backend/src/core/config.py` | modify | `r2_stale_after_seconds` |
| `backend/src/schemas/amenity_search.py` | new | `StartAmenitySearchRequest`, `OriginRequest`, `AmenitySearchRunResponse` |
| `backend/src/app/api/controllers/amenity_search.py` | new | view/typed error → status code + body |
| `backend/src/app/api/routes/amenity_search.py` | new | three route declarations + Swagger `responses` |
| `backend/src/app/api/dependencies/deep_search.py` | modify | `get_r2_run_coordinator` (503 when unconfigured) |
| `backend/src/app/main.py` | modify | composition root: shared clients, global semaphore, store, coordinator, `r2_tasks`, shutdown order |
| `backend/tests/services/deep_search/test_r2_run_lifecycle.py` | new | fake Places/Routes clients, fake R2 store, fake R1 output reader; R2-C8 tests |
| `backend/tests/services/deep_search/test_r1_pause_resume.py` | modify | `mark_finished` in `FakeRunStore`; R2-P1 tests |
| `backend/tests/services/deep_search/test_result_attachment.py` | modify | regression after the split |
| `backend/src/services/deep_search/feature_tests/test_r3_*.py` (5 files), `feature_sample_runs/R3.M1.4_url_discovery_and_web_search.py` | modify | build `SpecificMetricResolutionState` (drop `origin` / `radius_km`) |
| `backend/src/services/deep_search/feature_sample_runs/r1_step_persistence_sample_run.py` | modify | `mark_finished` on its row holder |
| `backend/src/services/deep_search/feature_sample_runs/r2_run_lifecycle_sample_run.py` | new | live, stage-by-stage retry of a run that failed after the discovery checkpoint |

No other new modules: the store and the coordinator own every new concern, as R1's do.

---

## 2. Contracts, Blueprint and Runtime Journey

### A. Feature Map

```
Feature: Deep Search
└─ Responsibility: AmenitySearch (R2) — places + predefined metrics per category (unchanged)
   ├─ Stage: run_place_discovery — M1.1, step `discovery` (unchanged body)
   ├─ Stage: run_accessibility_enrichment — M1.2, step `enrichment` (unchanged body)
   └─ Stage: run_result_attachment — M1.3, step `attachment` (unchanged body)
└─ Run lifecycle: R2RunCoordinator — start / retry / status around the store
   ├─ R2-C2 Step plan: R2_STEP_PLAN (contract, module tuple) + remaining_steps
   ├─ E1 Start workflow: start_run
   │  ├─ read_r1_output — R1's finished plans (R2-P1)
   │  ├─ create row — r2_runs running, attempts 0
   │  └─ _schedule — background task, 202
   ├─ E2 Retry workflow: retry_run
   │  ├─ _load_for_action — load + version check
   │  ├─ _precheck_retry — fast reject
   │  ├─ claim — one conditional update (R2-C5 guard)
   │  ├─ _claim_resume_step — failed step row → started
   │  └─ _schedule — resumed background task, 202
   ├─ E3 Status workflow: get_run
   │  ├─ in-memory live-task check (no I/O)
   │  └─ _view — row → view
   ├─ Background execution: _execute
   │  ├─ _new_amenity_search — per-run instance on shared clients
   │  ├─ _save_checkpoint — after discovery (SAVE, FENCE)
   │  ├─ _save_finished — finish write (FENCE)
   │  ├─ _save_failed — fail write (FENCE), retryable split
   │  └─ _record_step — step-row write after a matched run write
   ├─ Retryable split: _retryable_for + _is_config_error
   └─ shutdown — cancel + await live tasks
└─ Persistence: R2RunStore — r2_runs / r2_run_steps rows, codecs
└─ Persistence (R1, R2-P1): R1RunStore.mark_finished / get_finished_output
└─ HTTP: routes → controllers → coordinator
└─ (harness) test_r2_run_lifecycle.py, r2_run_lifecycle_sample_run.py — not in the request path
```

### B. Data Contracts

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
|---|---|---|---|---|
| `AmenitySearchState` | R2's own state | `origin: GeoPoint` · `radius_km: float` · `category_metric_plans` · `discovered_places` · `enrichment` · `predefined_records` (names, types, defaults unchanged) | **mutable**: each step writes its field | coordinator → step methods, store |
| `SpecificMetricResolutionState` | R3's own state | inputs `category_metric_plans`, `discovered_places={}`, `predefined_records={}`; outputs moved unchanged: `website_search_results`, `discovery_search_results`, `official_gate_results`, `resolution_results`, `specific_records`, `amenity_records` | mutable (R3) | R3 tests/runners → R3 |
| `AmenitySearchOutput` | R2 → R3 handoff (R2-C1) | `category_metric_plans` · `discovered_places` · `predefined_records` | immutable (frozen) | `_save_finished` → store `output`, `get_finished_output` |
| `R2RunStatus` | run status | `running` / `finished` / `failed` | n/a | store → coordinator |
| `R2StepName` | step plan names | `discovery` / `enrichment` / `attachment` | n/a | step plan |
| `R2StepId` | recorded step rows | `discovery` / `enrichment` | n/a | step rows |
| `R2StepRecord` | one decoded step row | `step_id` · `status: started/completed/failed` · `error_type` · `retryable` | immutable | store → coordinator |
| `R2RunRecord` | one decoded run row | `run_id` · `user_id` · `r1_run_id` · `status` · `state: AmenitySearchState` · `completed_step: "discovery" \| None` · `attempts` · `retryable` · `updated_at: str` · `output: AmenitySearchOutput \| None` · `steps: dict[R2StepId, R2StepRecord]` | immutable | `load_run` → coordinator |
| `R2RunView` | what the page sees | `run_id` · `status` · `completed_step` · `result: predefined_records \| None` · `retryable \| None` | immutable | coordinator → controller |
| State envelope | stored `state` | `{"version": R2_STATE_SCHEMA_VERSION, "state": {...}}` | n/a | store codec |
| Output envelope | stored `output` | `{"version": R2_STATE_SCHEMA_VERSION, "output": {...}}` | n/a | store codec |
| Step envelope | stored step `output` | `{"schema_version", "data"}`: `discovered_places` for discovery, `enrichment` for enrichment | n/a | store codec |
| `r1_runs.output` | R1 finished output | plain JSON list of `CategoryMetricPlan`; shape tied to `workflow_version` | write-once | `R1RunStore.mark_finished` → `get_finished_output` |
| `StartAmenitySearchRequest` | E1 body | `r1_run_id: UUID` · `origin: {latitude, longitude}` finite · `radius_km: float > 0, finite = 2.0` · extra forbidden | immutable | FastAPI → controller |
| `AmenitySearchRunResponse` | E1/E2/E3 body | `run_id` · `status` · `completed_step?` · `result?` · `retryable?` | immutable | controller |
| Error body | every error | R1's `RunErrorResponse` reused: `error`, `run_id?`, `status?`, `retryable` (always present when failed) | immutable | controller |

Rules surfaced: `completed_step` null until the first checkpoint; `output` non-null iff `finished` (database CHECK); "save as failed" never writes `state` or `completed_step`; `state` and `output` share one version constant.

**Columns** (`r2_runs`): `run_id uuid pk`, `user_id` → `auth.users` cascade, `r1_run_id` → `r1_runs` cascade, `status` check, `state jsonb not null`, `completed_step text` check `in ('discovery')` or null, `output jsonb`, `failure_stage`, `failure_message`, `retryable bool not null default false`, `attempts int >= 0`, `created_at`, `updated_at` (trigger, `clock_timestamp()`), CHECK output iff finished. `r2_run_steps`: as `r1_run_steps` with `step_id in ('discovery','enrichment')`, PK `(run_id, step_id)`, both checks, completed-immutable trigger.

### C. Supporting Actors & Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
|---|---|---|---|---|
| `GooglePlacesAsyncClient` | existing client, shared | `search_nearby_discovery`, `search_nearby_routing`, `aclose` | one | per-run `AmenitySearch` |
| `GoogleRoutesAsyncClient` | existing client, shared | `compute_route_matrix`, `aclose` | one | per-run `AmenitySearch` |
| Global Places semaphore | `asyncio.Semaphore(15)` | taken after the run slot on every Places call | one, built in `lifespan` | `AmenitySearch` |
| `R2RunStore` | concrete store | operations in §D | one (tests duck-type a fake) | `R2RunCoordinator` |
| `R1RunStore.get_finished_output` | concrete store method | `(run_id, user_id) -> list[CategoryMetricPlan] \| None [raises: StateVersionMismatchError, RunStoreError]` | one | `R2RunCoordinator.start_run` |
| Supabase `AsyncClient` | existing, service role, 10 s timeout | PostgREST builders | one | both stores |
| `StructuredLLMCaller` | existing, shared | not called by R2 M1; passed so per-run instances match today's composition | one | per-run `AmenitySearch` |
| `google.api_core.exceptions` | library | `InvalidArgument`, `FailedPrecondition`, `PermissionDenied` | n/a | `_is_config_error` |

### D. Class & Method Blueprint

**`AmenitySearch`** (modified constructor only)
| Method | Signature | Purpose (one line) |
|---|---|---|
| `__init__` | `(places_client, routes_client, *, llm_caller=None, owns_caller=True, places_concurrency=3, routes_concurrency=3, global_places_semaphore: Semaphore \| None = None, owns_clients: bool = True)` | adds the global cap and client ownership; defaults keep today's behavior |
| `execute_discovery`, `_route_one_mode` | unchanged signatures | take run slot, then global slot, around the Places call |
| `aclose` | `() -> None` | closes clients only when `owns_clients` |

**`R1RunStore`** (added)
| Method | Signature | Purpose (one line) |
|---|---|---|
| `mark_finished` | `(run_id, user_id, *, plans: list[CategoryMetricPlan]) -> bool` | sets `finished` and `output` in one UPDATE where `running` |
| `get_finished_output` | `(run_id, user_id) -> list[CategoryMetricPlan] \| None [raises: StateVersionMismatchError, RunStoreError]` | one SELECT of `output, workflow_version` for a finished run |
| `dump_r1_output` / `load_r1_output` | `(plans) -> list` / `(data) -> list[CategoryMetricPlan]` | plain-JSON codec via `TypeAdapter(list[CategoryMetricPlan])` |

**`R1RunCoordinator._settle`** (modified): finished → `mark_finished`; `needs_answers` → `set_status` as today.

**`R2RunStore`** (new, `r2_run_store.py`)
| Method | Signature | Purpose (one line) |
|---|---|---|
| `dump_state` / `load_state` | `(AmenitySearchState) -> dict` / `(dict) -> AmenitySearchState [raises: StateVersionMismatchError]` | versioned state envelope via `TypeAdapter` |
| `dump_output` / `load_output` | `(AmenitySearchOutput) -> dict` / `(dict) -> AmenitySearchOutput [raises: StateVersionMismatchError]` | versioned handoff envelope |
| `dump_step_output` / `load_step_output` | `(R2StepId, Any) -> dict` / `(R2StepId, dict) -> Any [raises: StateVersionMismatchError]` | R1's step envelope for the two recorded steps |
| `create_run` | `(run_id, user_id, r1_run_id, state) -> None [raises: RunStoreError]` | insert `running`, attempts 0, `completed_step` null |
| `save_checkpoint` | `(run_id, user_id, *, attempts, state, completed_step) -> bool` | write state + step where `running` at `attempts` |
| `save_finished` | `(run_id, user_id, *, attempts, state, output) -> bool` | write `finished`, state, output, `retryable=false`, fenced |
| `save_failed` | `(run_id, user_id, *, attempts, stage, message, retryable) -> bool` | write `failed` + failure columns, fenced; never touches state |
| `claim_retry` | `(run_id, user_id, *, expected_attempts, stale_before: datetime) -> bool` | the R2-C5 one-statement claim |
| `mark_version_mismatch` | `(run_id, user_id) -> None` | set `failed`, not retryable, stage `load_state`, unless `finished` |
| `load_run` | `(run_id, user_id) -> R2RunRecord \| None [raises: StateVersionMismatchError, RunStoreError]` | one read with embedded step rows; fails loudly if the embed is missing |
| `get_finished_output` | `(run_id, user_id) -> AmenitySearchOutput \| None` | R3's future read: output of a finished run only |
| `insert_step` | `(run_id, step_id, result) -> bool` | new `completed` row; False on duplicate key |
| `complete_claimed_step` | `(run_id, step_id, result) -> bool` | `started → completed` with output |
| `claim_failed_step` | `(run_id, step_id) -> bool` | `failed → started`, error cleared |
| `save_step_failed` | `(run_id, step_id, *, error_type, message, retryable, claimed) -> None` | new `failed` row, or `started → failed` |
| `_execute` | `(operation, query, *, conflict_ok=False) -> list[dict] [raises: RunStoreError]` | as R1: SDK/transport error → typed error + one log line |

**`R2RunCoordinator`** (new, `r2_run_coordinator.py`). Module constants: `MAX_RETRY_ATTEMPTS = 1`, `DEFAULT_STALE_AFTER_SECONDS = 600`, `SHUTDOWN_TIMEOUT_SECONDS = 5`, `R2_STEP_PLAN` (ordered `(name, call, checkpoint_after, recorded)` for discovery/enrichment/attachment).
| Method | Signature | Purpose (one line) |
|---|---|---|
| `__init__` | `(store, r1_store, *, places_client, routes_client, global_places_semaphore, llm_caller, stale_after_seconds=600)` | holds shared objects and the task set |
| `tasks` | property `-> dict[str, tuple[Task, str]]` | the live task set (`app.state.r2_tasks` is this object) |
| `start_run` | `(user_id, r1_run_id, origin: GeoPoint, radius_km: float) -> R2RunView [raises: RunNotFoundError, RunStoreError]` | read R1 output, create row, schedule task, `running` view |
| `retry_run` | `(user_id, run_id) -> R2RunView [raises: RunNotFoundError, RunConflictError, RunStoreError]` | load, pre-check, claim, claim step row, schedule resume |
| `get_run` | `(user_id, run_id) -> R2RunView [raises: RunNotFoundError, RunStoreError]` | memory check, then read-only row view |
| `shutdown` | `(timeout_seconds=5) -> None` | cancel every live task and await them |
| `remaining_steps` | `(completed_step) -> tuple[step specs]` (module function) | resume rule: null → all; discovery → enrichment on |
| `_schedule` | `(run_id, user_id, coro) -> None [mutates: self._tasks]` | create task with `run_id_var` set; done callback removes it |
| `_execute` | `(run_id, user_id, state, *, attempts, resume_after, claimed_step) -> None` | run remaining steps, checkpoint, finish; any error → `_save_failed` |
| `_new_amenity_search` | `() -> AmenitySearch` | per-run instance, `owns_clients=False`, `owns_caller=False` |
| `_save_checkpoint` | `(ctx, state) -> bool` | fenced checkpoint, then discovery step row |
| `_save_finished` | `(ctx, state) -> bool` | fenced finish write with output, then enrichment step row |
| `_save_failed` | `(ctx, exc, in_flight) -> None` | fenced fail write, then failed step row; store-down logged only |
| `_record_step` | `(ctx, step_id, result) -> bool` | insert or complete-claimed; conflict → stop, store error → log only |
| `_retryable_for` | `(exc, attempts) -> tuple[stage, retryable]` | the R2-C6 table plus D-R2-3 |
| `_is_config_error` | `(exc) -> type \| None` (module function) | walk `__cause__` ≤ 8 links for the three Google config errors |
| `_load_for_action` | `(user_id, run_id) -> R2RunRecord [raises: RunNotFoundError, RunConflictError]` | load; version mismatch → mark row, `409` |
| `_precheck_retry` | `(record) -> None [raises: RunConflictError]` | finished / not retryable / limit used / alive → `409` |
| `_is_stale` | `(record) -> bool [raises: RunStoreError]` | `running` and `updated_at` older than `stale_after` |
| `_view` | `(record) -> R2RunView` | row → view by status |

`ctx` is a small frozen dataclass inside the coordinator module: `run_id, user_id, attempts, claimed_step` (one execution's identity and fence). Not a public contract.

**Controllers** (`controllers/amenity_search.py`): `start_run(body, user, coordinator) -> 202`, `retry_run(run_id, user, coordinator) -> 202`, `get_run(run_id, user, coordinator) -> 200`, `_error_response(exc, *, not_found: str)`: `RunNotFoundError` → 404, `RunConflictError` → 409 with `run_id/status/retryable`, `RunStoreError` → 503, anything else re-raised (500).

**Routes** (`routes/amenity_search.py`): prefix `/api/amenity-search/runs`, router-level `Depends(get_authenticated_user)`, `POST ""`, `POST "/{run_id}/retry"`, `GET "/{run_id}"`, each with only the statuses its path can produce. Reuses `_UNAUTHENTICATED` and `_STORE_UNAVAILABLE` from the R1 routes module.

### E. Runtime Flow: Data Object Journey

**E1 start (request part, milliseconds)**
| # | Stage | Reads | Produces / mutates | Shape after |
|---|---|---|---|---|
| 1 | request model | JSON body | `StartAmenitySearchRequest` or `422` | typed origin, radius |
| 2 | `R1RunStore.get_finished_output` | `r1_run_id`, `user_id` | `list[CategoryMetricPlan]` or `404` / `503` | plans |
| 3 | build state | origin, radius, plans | `AmenitySearchState` | three inputs, outputs empty |
| 4 | `R2RunStore.create_run` | new `run_id`, state | row `running`, attempts 0 | row exists |
| 5 | `_schedule` | coro of `_execute(attempts=0, resume_after=None)` | `tasks[run_id] = (task, user_id)` | `202 {run_id, status: running}` |

**Background (`_execute`, seconds)**
| # | Stage | Reads | Produces / mutates | Shape after |
|---|---|---|---|---|
| 6 | `run_place_discovery` | state inputs | `[mutates: state.discovered_places]` | places per category |
| 7 | `_save_checkpoint` | state | row `completed_step=discovery`; then `discovery` step row | checkpoint saved |
| 8 | `run_accessibility_enrichment` | `discovered_places` | `[mutates: state.enrichment]` | bundles per place |
| 9 | `run_result_attachment` | places, enrichment, plans | `[mutates: state.predefined_records]` | records per category/place |
| 10 | `_save_finished` | final state | row `finished`, `output`; then `enrichment` step row | finished |
| 10' | `_save_failed` (any error at 6–10) | exception, `in_flight` | row `failed`, stage, `retryable`; failed step row if discovery/enrichment | state untouched |
| 11 | done callback | task | `tasks.pop(run_id)` (after the save) | not in memory |

**E2 retry**: `load_run` → `_precheck_retry` → `claim_retry` (attempts n → n+1) → `_claim_resume_step` → `_schedule(_execute(attempts=n+1, resume_after=completed_step, claimed_step))` → `202 {run_id, status: running, completed_step}`; the background then runs steps 8–11 (or 6–11 when `completed_step` is null), every write fenced on n+1.

**E3 status**: memory check (own live task → `running`; another user's → `404`) → `load_run` → `_view`.

**Transformation trace (shape only):**
```
StartAmenitySearchRequest{ r1_run_id, origin, radius_km }
 → list[CategoryMetricPlan]                                   # r1_runs.output
 → AmenitySearchState{ origin, radius_km, plans }             # r2_runs.state v1, running
 → + discovered_places{cat → {place_id → CanonicalPlace}}     # SAVE completed_step=discovery
 → + enrichment{place_id → EnrichmentBundle}
 → + predefined_records{cat → {place_id → PredefinedMetricsRecord}}
 → AmenitySearchOutput{ plans, discovered_places, predefined_records }   # r2_runs.output, finished
   | failed{ failure_stage, retryable }  (state and completed_step unchanged)
 → R2RunView{ status, completed_step, result | retryable }    # E3
```

**Approach at the decision points**
- **Resume position:** `completed_step` alone decides it (never empty outputs, since zero places is a valid result). Null → discovery; `discovery` → enrichment. Attachment is always recomputed.
- **The claim:** one UPDATE `SET status=running, attempts=n+1, retryable=false WHERE run_id AND user_id AND attempts=n AND ((status=failed AND retryable) OR (status=running AND updated_at < cutoff))`, expressed with `.or_()` and a quoted UTC `...Z` timestamp. Zero rows → `409` "Another retry of this run already started"; nothing scheduled.
- **The pre-check runs first** (cheap, not the guard): finished → 409; failed and (not retryable or attempts ≥ 1) → 409; running and not stale → 409 `status: running`; running, stale, attempts ≥ 1 → 409 (the reclaim is the retry).
- **Step-row claim:** the resume step's row is `failed` → `claim_failed_step`; if that returns False, the run is saved failed, not retryable, and `409` "start again". No row (stale reclaim, or attachment failed) → nothing to claim; the step is inserted at its write point.
- **Write order on every save:** run row (fenced) first. Zero rows → log `r2_run.superseded`, stop, no step row. Step row only after a match; duplicate/moved → log `r2_run.step_conflict`, stop; step-row store error → WARN, carry on.
- **Retryable split** (`_retryable_for`):

| Error | Stage | Retryable |
|---|---|---|
| `R2_PROVIDER_ERRORS` (`PlaceDiscoveryCallError`, `RoutingRetrievalError`, `TransitRetrievalError`), no config cause | `exc.stage` | `attempts < 1` |
| same, `__cause__` chain hits `InvalidArgument` / `FailedPrecondition` / `PermissionDenied` | `exc.stage` | false, ERROR `r2_run.config_error` |
| `PlaceDiscoveryRequestError`, `ResultAssemblyError` | `exc.stage` | false |
| `RunStoreError` on checkpoint/finish (D-R2-3) | `run_store` | `attempts < 1` |
| `CancelledError` (shutdown) | `cancelled` | `attempts < 1`, then re-raise |
| anything else | `unexpected` | false, `logger.exception` |

### F. Method Detail

**`R2RunCoordinator._execute`**
- **Purpose:** one execution of the remaining steps, ending in exactly one fenced terminal write.
- **What it does:** builds a per-run `AmenitySearch`; iterates `remaining_steps(resume_after)`; sets `in_flight` to the step's id when the step is recorded (discovery, enrichment) and None for attachment; awaits async steps, calls attachment inline; after discovery calls `_save_checkpoint` and stops if it returns False; after the last step calls `_save_finished`. Any exception goes to `_save_failed(ctx, exc, in_flight)`; `CancelledError` is saved then re-raised. A lost fence or step conflict ends the task quietly (already logged).
- **Inputs:** `run_id, user_id, state, attempts, resume_after, claimed_step` · **Outputs:** none (row is the result) · **Failure:** never raises except `CancelledError`.

**`R2RunCoordinator._schedule`**
- Sets `run_id_var` before `create_task`, so the task's context carries the run id for every log line.
- Done callback removes the entry only if it is still this task (a reclaimed run may have a newer entry), and logs `r2_run.task_crashed` (ERROR) if the task ended with a non-cancel exception (`_save_failed` itself failing on a bug).

**`R2RunCoordinator.get_run`**
- Memory check first, no I/O: own live task → `running` with no `completed_step`; another user's → `RunNotFoundError`. Not found → `load_run`.
- `StateVersionMismatchError` → `failed`, not retryable, WARN `r2_run.status_degraded`, no write. `None` → `RunNotFoundError`. `RunStoreError` → propagates (503).
- `_view`: running → `completed_step`; finished → `result = output.predefined_records`; failed → `retryable` from the row (already `rule AND attempts < 1` at write time).
- A stale `running` row still reads `running` (A5 left open by the spec).

**`R2RunCoordinator.shutdown`**
- Cancels every task in `tasks`, then `asyncio.wait(..., timeout)`. Each task saves itself as failed before ending. Called by `lifespan` before the shared Places/Routes clients, the LLM caller and the database client close (the fail write needs the database).

**`R1RunStore.get_finished_output`**
- One SELECT `output, workflow_version` filtered on `run_id`, `user_id`, `status = 'finished'`. No row, or `output` null (pre-column run) → None. `workflow_version` ≠ `R1_WORKFLOW_VERSION` → `StateVersionMismatchError` (the coordinator turns it into `404`, logged `reason=r1_version_mismatch`).

**`R2RunStore.load_run`**
- `select("*, r2_run_steps(step_id, status, error_type, retryable)")`; missing or non-list embed → `RunStoreError` (fail loudly, as R1). Decodes `state` always and `output` when present; either version mismatch raises.

**`_is_config_error`**
- Follows `__cause__` from the R2 error (R2 error → `PlacesClientError`/`RoutesClientError` → Google error), at most 8 links, returns the first link that is one of the three config classes. Only consulted for `R2_PROVIDER_ERRORS`.

---

## 3. Async Structure

| Layer / group | Operations and I/O | Data dependency | Placement | Ordering |
|---|---|---|---|---|
| HTTP route → controller → coordinator | one coroutine per request | n/a | event loop | awaited |
| E1 request part | `get_finished_output` → `create_run` → `create_task` | the row needs the plans; the task needs the row | event loop (async PostgREST client) | sequential |
| E2 request part | `load_run` → `claim_retry` → `claim_failed_step` → `create_task` | the step claim is valid only after the run claim wins | event loop | sequential |
| E3 | memory lookup (no I/O) → `load_run` | the read only happens on a miss | event loop | sequential |
| Background task, step level | discovery → checkpoint → enrichment → attachment → finish | each step reads the previous step's field; the checkpoint must land before enrichment's paid calls | event loop, its own task | sequential |
| Inside discovery / enrichment | per-category `searchNearby`; per category×mode routing; transit batches | independent (unchanged code) | event loop | concurrent via `gather`, bounded by run semaphore (3) then global semaphore (15) |
| Attachment | pure in-memory join | n/a | inline in the task (CPU, milliseconds) | sequential |
| Save writes | run-row UPDATE → step-row write | the step row follows only a matched run write | event loop | sequential |
| Different runs | separate tasks | independent | event loop | concurrent (one task per run, scheduled with `create_task`) |
| Shutdown | cancel all → `asyncio.wait(timeout)` → close clients | the clients must outlive the tasks' fail writes | event loop | concurrent cancel, then sequential close |

**Blocking check:** no blocking calls. Places/Routes are async gRPC clients, Supabase is the async client with a 10 s PostgREST timeout, and the codecs (`TypeAdapter` on at most tens of places) are milliseconds of CPU, so they run inline. No thread or process worker is needed.

**Shared state:** each task owns its own `AmenitySearchState` and `AmenitySearch` instance (one-object model per run, no sharing). The only shared mutable objects are the task dict (touched only on the event-loop thread: `_schedule` and the done callback) and the two semaphores (designed for sharing). A task is referenced from the dict until it ends, so it can't be garbage-collected mid-run.

---

## 4. Drift Entries (per method)

**`R2RunCoordinator.start_run`**
- **Core behavior:** read R1's finished plans, create the row, schedule the task.
- **Drifts handled:**
  - **Bad origin/radius/body.** Caught at the **edge** (request model: finite floats, `radius_km > 0`, extra fields forbidden); **rejected** `422`, no row.
  - **R1 run missing, another user's, unfinished, pre-column, or other version.** **Core** (`get_finished_output` returns None or raises mismatch); **rejected** `404`, no row.
  - **Database down before the row.** **Infra** (store); **propagated** as `RunStoreError` → `503`, no row.
- **Left out (why):**
  - Latitude/longitude range checks: Google rejects them with `InvalidArgument`, which the config-error check makes non-retryable. *Wrong boundary (not invented as policy here).*
  - Deduplicating two starts for one R1 run: allowed by R2-C6. *Not live.*
  - Retrying the R1 read: R2-P1 says no retry; `503` means try again. *Trust.*

**`R2RunCoordinator.retry_run`**
- **Core behavior:** claim once, resume after `completed_step`.
- **Drifts handled:**
  - **Two retries at once.** **Infra** (one conditional UPDATE); **reject** `409` for the loser, nothing scheduled.
  - **Run still alive.** **Core** (`_precheck_retry`, `_is_stale`); **reject** `409 status: running`.
  - **Finished, not retryable, or limit used.** **Core**; **reject** `409`.
  - **Saved under another version.** **Core** (`_load_for_action`); **reject**: row marked failed, not retryable, `409`.
  - **The failed step row moved after the run claim won.** **Core**; **reject**: run saved failed, not retryable, `409` "start again".
- **Left out (why):**
  - A `started` step row on a stale reclaim: a `started` row only exists after a claim (attempts ≥ 1), and a reclaim needs attempts 0. *Not live.*
  - A resume step whose row is already `completed`: the enrichment row is written only after the run is finished, and the discovery row only after `completed_step` is saved. *Not live.*

**`R2RunCoordinator._execute`**
- **Core behavior:** run the remaining steps and settle the row once.
- **Drifts handled:**
  - **A Places/Routes call fails.** **Core** (`_retryable_for`); **reject** to the row: `failed`, retryable per the table.
  - **Config cause behind a provider error.** **Core** (`_is_config_error`); **reject**: not retryable, ERROR `r2_run.config_error`.
  - **Shutdown cancels the task.** **Core**; **recover**: saved failed with `attempts < 1`, then re-raised.
  - **A newer execution owns the row** (lost fence). **Infra** (the `attempts` filter); **stop**: INFO `r2_run.superseded`, no further writes.
  - **`gather` inside a step fails fast and leaves sibling calls running.** Unchanged R2 code; the whole step is the unit of recovery and its results are discarded. *Accepted by spec ("the whole step is the unit").*
- **Left out (why):**
  - Saving after enrichment: rule 2 of the persistence rule; risk accepted in R2-C2. *Trust.*
  - Re-validating the loaded state against the plans: the codec rebuilds the exact saved types. *Trust.*
  - A timeout around a whole step: every Places/Routes call already has a 15 s per-attempt timeout and bounded retries. *Wrong boundary (infra already bounds it).*
  - The claimed enrichment row stays `started` if attachment then fails: record-only table, run is not retryable after its one retry. *Trust.*

**`R2RunCoordinator._save_checkpoint` / `_save_finished` / `_save_failed`**
- **Core behavior:** one fenced run-row write, then the step row.
- **Drifts handled:**
  - **Database error on the run write.** **Infra**; checkpoint/finish → `_save_failed` with stage `run_store` (D-R2-3); fail write itself failing → **logged** ERROR `r2_run.failed_not_saved`, row stays `running` and is reclaimable after `stale_after`.
  - **Step row duplicate or moved.** **Infra** (PK `23505` / status filter); **stop**, INFO `r2_run.step_conflict`.
  - **Step row store error.** **Infra**; **recover-degrade**: WARN `r2_run.step_record_failed`, run continues (A24).
- **Left out (why):**
  - A transaction across both tables: PostgREST has none; the write order keeps the run row right. *Accepted (R2-C4 Iteration 1).*
  - Retrying a failed write: unsafe without knowing whether it landed; stale reclaim covers it. *Trust.*

**`R2RunCoordinator.get_run`**
- **Core behavior:** read-only status.
- **Drifts handled:**
  - **Another user's live task.** **Core** (memory check keeps `user_id`); **reject** `404` (A23).
  - **Version mismatch.** **Core**; **degrade**: `failed`, not retryable, WARN, no write.
  - **Database down.** **Infra**; **propagate** `503`.
- **Left out (why):**
  - A stale `running` row reported as retryable: A5 is left open by the spec. *Not decided here.*
  - Another worker's live task: falls through to the row read, correct and slower (A22). *Not live at one process.*

**`R2RunCoordinator.shutdown`**
- **Core behavior:** cancel and await live tasks before the clients close.
- **Drifts handled:**
  - **A task's fail write outlasts the timeout.** **Infra**; **degrade**: WARN `r2_run.shutdown_timeout` with the pending run ids; rows stay `running` and are reclaimable (A21).
- **Left out (why):**
  - New starts during shutdown: uvicorn stops accepting requests before lifespan teardown. *Not live.*

**`R2RunStore.load_run`**
- **Core behavior:** one read of the run with its step rows.
- **Drifts handled:**
  - **Embed missing.** **Infra**; **reject** `RunStoreError` (de-masked; never "no steps").
  - **State/output version differs.** **Core** (codec); **reject** `StateVersionMismatchError`.
  - **`updated_at` not ISO.** `_is_stale` raises `RunStoreError`, loud, never a silent "not stale".
- **Left out (why):**
  - Payload size: 10 places × categories, well under PostgREST limits. *Imaginary.*

**`R2RunStore.claim_retry`**
- **Core behavior:** the single winner of a retry.
- **Drifts handled:**
  - **Timestamp format in the `or_` filter.** **Infra**; the cutoff is formatted as a quoted UTC `Z` string. The fakes cannot prove it (A6), so it is a manual check on the dev database (§7). *De-mask: a malformed filter is a loud `APIError` → `503`, never a silent "no match".*
- **Left out (why):**
  - The two-update fallback from A6: only needed if `or_` fails on the dev database. *Unknown: confirm first.*

**`AmenitySearch` slot order**
- **Core behavior:** run slot, then global slot, per Places call.
- **Drifts handled:**
  - **Busy runs hoarding global slots.** **Core**: a run waiting on its own limit never holds a global slot (enter order).
- **Left out (why):**
  - A global cap for the Routes matrix: ⌈P/100⌉ calls per run. *Not live (R2-C2 Iteration 1).*
  - Multi-worker caps: one process at MVP. *Accepted (A19).*

**`R1RunStore.mark_finished` / `get_finished_output`**
- **Core behavior:** write-once output with the status; read it back for R2.
- **Drifts handled:**
  - **Status and output written apart.** **Infra**: one UPDATE plus the CHECK (A18).
  - **Pre-column finished runs.** **Core**: `output` null → None → `404` (A17).
- **Left out (why):**
  - Backfilling old rows: no backfill (MVP). *Decided by spec.*

---

## 5. Log Plan

All lines are JSON on `DEEP_SEARCH_LOGGER_NAME`, carry `run_id` (`run_id_var`, set before `create_task` so task lines inherit it) and `user_id`. R2's own stage lines (`discovery.*`, `enrichment.*`, `attachment.*` on `PLACES_LOGGER_NAME`) are unchanged and pick up `run_id` from the same context variable.

| Event | Level | Node type | Driving state |
|---|---|---|---|
| `r2_run.created` | INFO | state change | `r1_run_id`, `category_count`, `radius_km`, `schema_version` |
| `r2_run.rejected` | INFO | boundary (reject handled) | `reason` (r1_not_found, r1_version_mismatch, not_found, finished, not_retryable, still_running, cas_lost, step_conflict, version_mismatch), `status` |
| `r2_run.loaded` | INFO | boundary (database in) | `status`, `attempts`, `completed_step`, `retryable`, `step_statuses` |
| `r2_run.retry_started` | INFO | state change | `attempts`, `resume_after`, `claimed_step`, `reclaimed_stale` |
| `r2_run.checkpoint_saved` | INFO | state change | `completed_step`, `attempts`, `place_counts`, `state_chars` |
| `r2_run.finished` | INFO | state change | `attempts`, `record_counts`, `path` (start / retry) |
| `r2_step.saved` | INFO | state change | `step_id`, `path` (insert / claimed) |
| `r2_run.failed` | ERROR | endpoint | `stage`, `step_id` (in_flight), `error_class`, `retryable`, `attempts`, `message` (`logger.exception` for unexpected) |
| `r2_run.config_error` | ERROR | endpoint detail | `step_id`, `google_error_class` |
| `r2_run.superseded` | INFO | boundary (fence lost) | `operation`, `attempts` |
| `r2_run.step_conflict` | INFO | boundary (reject) | `step_id`, `path` |
| `r2_run.step_record_failed` | WARN | silent drift | `step_id`, `operation`, `store_error` |
| `r2_run.failed_not_saved` | ERROR | silent drift | `stage`, `store_error` |
| `r2_run.status_degraded` | WARN | silent drift | `found_version`, `expected_version` |
| `r2_run.shutdown_timeout` | WARN | silent drift | `pending_run_ids`, `timeout_seconds` |
| `r2_run.task_crashed` | ERROR | endpoint | `error_class` |
| `r2_run.store_error` | ERROR | boundary (database out) | `operation`, `error_class`, `detail` (as R1's) |

No line per step start, per resume skip or per memory-check hit: they are deterministic from lines already logged (`retry_started.resume_after`, the 202, the status reply). No line for E3 hits served from memory (polling every 2 s would flood the log).

---

## 6. Sample Runner and Fixture Set

### 6.1 Live sample runner: `feature_sample_runs/r2_run_lifecycle_sample_run.py` (new)

**How to run it:** from `backend/` (needs `GOOGLE_MAPS_API` and network; no Supabase):

```bash
python -m src.services.deep_search.feature_sample_runs.r2_run_lifecycle_sample_run
```

**What it seeds** (no earlier mechanism is re-run; discovery is never called):
- An in-memory row holder with `R2RunStore`'s method names and the real `dump_state` / `load_state` / `dump_output` / step codecs, so every saved object round-trips as the database would.
- One `r2_runs` row as a run that **failed in enrichment after its discovery checkpoint**: `status=failed`, `retryable=true`, `attempts=0`, `completed_step="discovery"`, `failure_stage="retrieve_transit"`.
- Its state: origin (50.130034, 8.628251), radius 2 km, the `swimming_pool` / `operating_details` and `bakery` / `basic_profile` plans, and `discovered_places` loaded from the real M1.1 capture `data/m1_1_discovered_places.json` (D-R2-4: enrichment joins by `place_id` against a live re-search at the same origin). R2 has no prompt worked pairs, so the worked-pair rule is met.
- A `failed`, retryable `enrichment` step row and a `completed` `discovery` step row.
- A fake R1 output reader is not needed (retry never reads R1).

**What it drives:** the real `R2RunCoordinator.retry_run` with the real shared Places/Routes clients and a global semaphore of 15, awaits the scheduled task, then calls `get_run`. Live calls: routing re-search (2 categories × 3 modes) and one transit batch.

**What it prints, one titled section each:**
1. Seeded run row and step rows (status, attempts, `completed_step`, place counts per category).
2. Pre-check and claim: attempts 0 → 1, `enrichment` step `failed → started`.
3. Discovery calls during the resume (must be 0, counted from `discovery.*` events).
4. Enrichment Google calls: `enrichment.mode_completed` and `enrichment.transit_batch_completed` events read back with a collecting handler on `PLACES_LOGGER_NAME`, as `accessibility_enrichment_sample_run.py` does.
5. Attachment trail: `attachment.completed` and any `attachment.accessibility_degraded` (A3 visible if the live re-search moved).
6. The finish write: row status, `output` size, step rows (`enrichment` now `completed` via the claimed path).
7. The status read: `R2RunView` with `result` record counts and two sample records (name, walk/drive/transit minutes).
8. The run's `r2_run.*` lifecycle lines in order.

**On a typed failure:** the failed row's `failure_stage`, `retryable`, the exception class and message, exit code 1. Nothing is written to Supabase or to disk.

### 6.2 Fixture set (pytest, no live calls): `tests/services/deep_search/test_r2_run_lifecycle.py`

**Fakes:**
- `FakePlacesClient` / `FakeRoutesClient`: fixed responses per request, call counts per kind (discovery vs routing vs transit), and injectable failures raised **with the real `__cause__` chain** (`PlacesClientError` from `PermissionDenied`, `ServiceUnavailable`, …).
- `FakeR2RunStore`: in-memory rows applying the SQL rules, each next to a comment naming the condition it copies: `user_id` filter, `status=running AND attempts=n` fence, the claim OR condition with a test clock for `updated_at`, "save as failed never touches state", output iff finished, PK on step rows, completed-immutable. Every state/output/step payload round-trips through the real codecs and JSON.
- `FakeR1Output`: `get_finished_output` over in-memory finished R1 rows.

| Test | Passes when |
|---|---|
| parity | the coordinator's step plan and a direct call of the three methods give the same final state (`dump_state` equal) |
| resume parity | an enrichment failure then a retry gives the same final state as a clean run; discovery called once in total |
| no checkpoint after enrichment | an attachment failure leaves `completed_step = discovery` |
| failed keeps checkpoint | save-as-failed leaves `state` and `completed_step` unchanged |
| round trip | initial, after-discovery, finished states and the output come back equal, including the real `m1_1_discovered_places.json` capture |
| version mismatch | retry → `409`, row failed not retryable; status → `failed`, `retryable:false`, no write |
| concurrent retries | two `retry_run` calls gathered: exactly one schedules, the other gets `409` |
| stale reclaim | a `running` row older than `stale_after` (test clock) is claimed; a fresh one gets `409 running`; a stale one at attempts 1 gets `409` |
| fencing | a write with an old `attempts` matches nothing and adds no step row |
| retry limit | a second failure after a retry is saved `retryable:false` |
| retryable split | each row of the §2E table gives its `stage` / `retryable`; `PermissionDenied` under each of the three provider errors → false + one `r2_run.config_error`; `ServiceUnavailable` → true |
| database blip (D-R2-3) | a `RunStoreError` on the checkpoint saves `failed`, stage `run_store`, retryable |
| ownership | another user's run: start (R1 row), retry and status all `404`, store finds nothing |
| step rows | clean run: completed `discovery` + `enrichment`, none for attachment; enrichment failure: failed row with the run's `retryable`, retry moves it `started → completed`; attachment failure then retry adds `enrichment` once; lost fence adds no row |
| background lifecycle | start and retry return before discovery starts (a gate event in the fake client); `shutdown` mid-run saves `failed` + `retryable` before the fake clients' `aclose`; `tasks` is empty after completion |
| E3 memory check | while a task is live, status answers `running` with zero store reads; another user's id gets `404`; after the task ends, status reads the row |
| global cap | with 6 runs at once, in-flight Places calls never exceed 15 and never 3 per run |
| HTTP | via `ASGITransport` with dependency overrides: `401` without cookie on all three, `422` bad origin/radius/extra field, `404`, `202` bodies, `409` bodies with `retryable`, `503` store down, `503` when the coordinator is not configured |

**R2-P1 block in `test_r1_pause_resume.py`:** a finished R1 run stores `output` in the same write as `finished` (fake store asserts one call), `get_finished_output` returns its plans; running, `needs_answers`, failed, another user's, pre-column (`output` None) → None; another `workflow_version` → `StateVersionMismatchError`.

**Regression:** existing R2 tests, the 5 R3 feature tests, and the R1 suite pass after the split (the 37 baseline failures are pre-existing and unrelated: MCP gateway, login, mechanisms 4–6, R3.M2.2).

---

## 7. Verification

1. `cd backend && python -m pytest tests src/services/deep_search/feature_tests -q`: §6.2 passes, and the failure list equals the saved baseline (37, none new).
2. `python -m src.services.deep_search.feature_sample_runs.r2_run_lifecycle_sample_run`: section 3 shows 0 discovery calls, section 6 shows `finished` with the `enrichment` row `completed`, section 7 shows records.
3. **By hand on the dev database (not automated, R2-C8 Iteration 1):** apply the three migrations twice (safe to re-run); confirm the `NOT VALID` CHECK on `r1_runs`; confirm the `r2_runs.updated_at` trigger moves on update; run one `claim_retry` against a stale row and a fresh row to prove the `or_` filter and timestamp format (A6).
4. **Manual HTTP (Swagger):** finish an R1 run → `POST /api/amenity-search/runs` → `202`; poll `GET` → `running` → `finished` with `result`; break the key → `failed`, `retryable:false` (config error); `POST .../retry` on a retryable failure → `202` and only enrichment calls in the log.

---

## 8. Architecture & Modularity Decisions

### Layer 1: Glance

- **Shape:** a concrete run coordinator drives R2's three unchanged step methods inside one background task per run, around a concrete Supabase store; the composition root shares the Google clients and one global Places semaphore across per-run `AmenitySearch` instances.
- **Seams:**
  - Coordinator ↔ `AmenitySearch`: the coordinator decides order, saves and retries; R2 decides what each step computes.
  - Coordinator ↔ `R2RunStore`: only the store knows tables, PostgREST errors and payload versions.
  - R2 ↔ R1: one read of `r1_runs.output`; R2 never replays R1.
  - R2 state ↔ R3 state: separate classes; the handoff is `AmenitySearchOutput`.
- **Components:**
  - `AmenitySearch` — R2 step logic (unchanged), now with a global slot and client ownership flag.
  - `R2RunCoordinator` — step plan, guard, background tasks, retryable split, status.
  - `R2RunStore` — `r2_runs` / `r2_run_steps` rows and codecs.
  - `R1RunStore` (+2 methods) — R1's finished output.
  - Routes / controllers / dependency — HTTP translation only.

### Layer 2: Justification

**B. Component Map**

| Component | Owns | Depends on | Abstracted? |
|---|---|---|---|
| AmenitySearch | discovery, enrichment, attachment (unchanged) | Places/Routes clients, two semaphores | — (concrete) |
| R2RunCoordinator | statuses, resume rule, fence, claim, retryable split, task set | AmenitySearch, R2RunStore, R1RunStore | — (concrete) |
| R2RunStore | SQL-facing rows, codecs, versions | Supabase AsyncClient | — (concrete) |
| R1RunStore | R1 rows + finished output | Supabase AsyncClient | — (concrete) |
| controllers/routes | status codes and bodies | R2RunCoordinator | — (concrete) |

**C. Decisions & Justifications**

| Decision | Current requirement that forced it | What breaks today without it |
|---|---|---|
| Two state classes (R2-C1 approach 1) | each service holds only its own data | R2 saves R3's empty fields; R3 can overwrite R2's |
| Step plan tuple in the coordinator (R2-C2 approach 1) | resume after `completed_step`, service unchanged | no way to skip saved discovery |
| One versioned `state` blob + `completed_step` (R2-C4 approach 1) | status and data change in one update | partial checkpoints; R1 layout diverges |
| Separate `output` column | R3 reads a small stable contract | R3 must decode R2's whole state |
| `r2_run_steps` record table | R2-C4 Iteration 1, same model as R1 | no per-step record for failures and retries |
| `attempts` fence on every write | a late older execution must not overwrite | stale reclaim lets two executions write one row |
| Claim with stale condition (R2-C5 approach 2) | a crashed run must stay retryable | a restart leaves the run unretryable forever |
| Background task + task set (R2-C6 Iteration 2) | refresh must not lose `run_id` or stop the run | page has no `run_id` until the run ends |
| In-memory E3 check | polling every 2 s; ownership before the row read | every poll reads the database; A23 leak |
| Per-run `AmenitySearch` + global semaphore | per-customer limit 3, process cap 15 | one customer's run queues behind all others |
| `owns_clients` flag | per-run instances must not close shared clients | first finished run closes the clients for everyone |
| `_is_config_error` | config errors must not offer Retry | a bad key burns the one retry and fails again |
| `r2_stale_after_seconds` setting | "10 minutes, as a setting" (R2-C5) | value hard-coded |
| `mark_finished` (R2-P1) | finished and output in one UPDATE | a crash between writes leaves finished with no output |

**D. Kept Concrete / Rejected**

| Considered | Decision | Reason |
|---|---|---|
| `RunStore` Protocol for R2 | kept concrete | one implementation; the fake duck-types it, as R1's |
| Factory callable for `AmenitySearch` | not added | the coordinator calls the constructor with keywords; tests inject fake clients |
| `AmenitySearch.run(resume_after, on_step_completed)` (R2-C2 approach 2) | rejected | R2 has no run-scoped resources to keep alive across steps |
| Generic run base class shared with R1 | not added | R1 and R2 differ in tables, statuses and execution model |
| `R2RunFailedError` | not added (D-R2-5) | post-202 failures are saved on the row; no catcher exists |
| 502/503/500 mapping for run failures | not added | the codes no longer reach the page (Iteration 2) |
| External job queue | rejected (R2-C6 approach 3) | no Redis/worker exists; runs take seconds |
| Heartbeat lease | rejected (R2-C5 approach 3) | timer per run for a rare crash case |
| Separate module for the task set | not added | only the coordinator schedules and checks tasks |
| R1 status endpoint reading `output` | not built (D-R2-2) | outside R2; pre-column rows still need replay |
| Global cap for Routes | not added | ⌈P/100⌉ calls per run (R2-C2 Iteration 1) |

### Layer 3: Wiring

**E. Dependency Direction**
```
routes → controllers → R2RunCoordinator → AmenitySearch (per run) → GooglePlaces/RoutesAsyncClient (shared)
                                        → R2RunStore → Supabase AsyncClient
                                        → R1RunStore.get_finished_output → Supabase AsyncClient
AmenitySearchState / SpecificMetricResolutionState / R2 contracts ← feature_schemas/schemas.py (no outward deps)
```

**F. Composition Root**
- **Where:** `src/app/main.py` `lifespan`, inside the existing `if settings.supabase_service_role_key:` block.
- **Selects:** `create_places_async_client(settings)`, `create_routes_async_client(settings)`, `asyncio.Semaphore(GLOBAL_PLACES_CONCURRENCY)`, `R2RunStore(db_client)`, the existing `R1RunStore`, the shared `llm_caller`, and `R2RunCoordinator(..., stale_after_seconds=settings.r2_stale_after_seconds)`. Sets `app.state.r2_run_coordinator` and `app.state.r2_tasks = coordinator.tasks`; both None when the key is unset (`503`).
- **Teardown order:** `coordinator.shutdown()` → Places/Routes `aclose()` → `llm_caller.aclose()` → `db_client.postgrest.aclose()`.

**G. End-to-End Flow**
1. The request enters a route behind `get_authenticated_user` (`401` otherwise); the body is validated (`422`).
2. The controller calls the coordinator with the verified `user_id`.
3. Start reads R1's output (`404`/`503`), creates the row, schedules the task and returns `202`; retry loads, pre-checks, claims (`409` on loss) and returns `202`; status checks memory, then the row.
4. The task builds a per-run `AmenitySearch`, runs the remaining steps, checkpoints after discovery, and writes `finished` or `failed` with the fence.
5. The page polls status until `finished` (render `predefined_records`) or `failed` (Retry or Start again).

### Layer 4: Backing (reasoning for Layer 3)

- **Why the coordinator, not `AmenitySearch`, holds the step plan:** the steps are already public methods and R2 has no per-run resources, so persistence knowledge stays out of the service and the scope rule ("step methods unchanged") holds.
- **Why per-run instances on shared clients:** the run semaphore must be per customer, while gRPC channels are expensive to open; sharing clients and the global semaphore from the composition root gives both.
- **Why the task set lives on the coordinator and is exposed as `app.state.r2_tasks`:** scheduling, the done callback and the E3 check all need it, and tests reach it without an app; `lifespan` only needs `shutdown()`.
- **Why `get_finished_output` lives on `R1RunStore`:** it is the only module that knows `r1_runs`; R2 depends on its typed result, not on R1's table.
- **Why shutdown runs before the clients close:** a cancelled task saves its failure through the database client and may still be inside a Places call; closing clients first would turn a clean cancel into a client error.

---

## 9. Build Notes (found while implementing)

- **`PredefinedMetricsRecord.price_level` annotation corrected to `int | None`.** The round-trip test on the real M1.1 capture failed: `Place.to_dict` returns the Places `PriceLevel` enum as an int, while the field was annotated `str | None`. The value M1.3 writes is unchanged; only the annotation now matches it, so the state codec loads it back exactly (R2-C3).
- **App-wide 422 handler for non-finite input.** A `NaN` or `1e999` (valid JSON that parses to infinity) in a body was rejected by the model, but FastAPI's default 422 handler echoes the input and cannot JSON-encode it, so the request ended as a 500. `src/app/main.py` now renders such inputs as text; every route answers 422.
- **The finish write clears `failure_stage` / `failure_message`.** Seen in the sample-runner dry run: a retried run that finished still carried its earlier failure stage.
- **Live sample runner not executed in the build environment.** `backend/.env` has no `GOOGLE_MAPS_API`. The runner was exercised end to end with fake Google clients from a scratch script (claim, 0 discovery calls, enrichment, finish write, claimed step `started → completed`, status read). Run it live with the key set.
- **Tests:** 522 pass (46 new: 42 in `test_r2_run_lifecycle.py`, 4 R2-P1 in `test_r1_pause_resume.py`); the 37 failures are the pre-existing baseline (MCP gateway, login, mechanisms 4–6, R3.M2.2), unchanged.
