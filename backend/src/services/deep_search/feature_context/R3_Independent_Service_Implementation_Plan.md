# R3 Specific Metric Resolution as an Independent Service: Implementation Plan

## Context

R3 (Specific Metric Resolution) works today only in-process: one call of `run_specific_metric_resolution(state)` with one gateway, no row, no retry, no resume. A failure in STEP 4 throws away STEP 3's paid LLM and web work. Two parallel runs would also make twice the provider calls on one account. The R3 sections of [R2_R3_Independent_Services_Problem_Context.md](backend/src/services/deep_search/feature_context/R2_R3_Independent_Services_Problem_Context.md) (R3-C1 to R3-C9, with their iterations) and Part B of [R2_R3_HTTP_Traceflow.md](backend/src/services/deep_search/feature_context/R2_R3_HTTP_Traceflow.md) define the fix. This plan builds it. R3-C1 (the state split) already shipped with R2.

**What gets built:**
- `r3_runs` + `r3_run_steps` tables (with the `degraded` step status), a store and a tuple-key state codec (R3-C4, R3-C5 + Iteration 1).
- A resume point and a save callback on R3's one entry method; nothing else in STEP 1 to STEP 5 changes (R3-C3). The callback saves STEP 3's results the moment STEP 3 ends. The resume point (`resume_after = "discovery_batch"`) lets a retry skip STEP 3 and start at STEP 4, so a failure in STEP 4 doesn't make the retry pay for website discovery again or get different websites.
- One app-wide limit per web provider behind each run's own limit: Parallel 10 slots, Firecrawl 2 slots + 10/min (R3-C2 Iteration 1).
- A coordinator: per-run R3 instance, background task, STEP 3 checkpoint, fenced writes, atomic retry claim (failed + retryable, or running + stale), retryable split with the gateway config-error check, status from memory, ordered shutdown (R3-C6, R3-C7 + Iterations 1 and 2).
- Three endpoints under `/api/specific-metric-resolution/runs`: start `202`, retry `202`, status `200` (R3-C8).
- Fake-based tests, a manual SQL check list, and a live sample runner (R3-C9).

**What does not change:** every STEP 1 to STEP 5 decision, degradation and log line, the breaker, the gateway's sessions, retries, timeouts, parsing and failure kinds, and every object R3 produces. Given the same provider responses, R3's output is identical.

**Decisions taken in this plan (beyond the spec):**
- **D-R3-1, the evidence store's lookup table is rebuilt on load.** Found while planning: `MetricsSourceContent._index` (inside every `AmenityResolutionRecord.phase1`) is keyed by a `(source_kind, url, shaped_text)` tuple and fails to reload (`Input should be a valid tuple`), the same bug R3-C4 names for the four state dicts. Checked in a scratch run: the codec writes `_index` as `{}` and the loader rebuilds it from `items`. The record then compares equal, and the index points at the same item objects. No schema change.
- **D-R3-2, no `R3RunStore.get_finished_output`.** No service reads R3's output yet (STEP 6 is unbuilt, and R3 is the last stage). Status reads `output` through `load_run`. It is added when a reader exists.
- **D-R3-3, the coordinator takes a zero-argument service factory.** Lifespan binds `create_specific_metric_resolution` to settings, the shared caller and the app-wide limits. Each run calls it once (R3-C2), and tests pass a factory that returns an R3 instance on a fake gateway.
- **D-R3-4, the status view carries the result already encoded.** `R3RunView.result` is the JSON-ready list of `{category_id, place_id, value}` built by the store codec. FastAPI's own encoder can't handle `_index`'s tuple keys, so the controller never encodes R3 objects itself.
- **D-R3-5, R3's store imports `stale_cutoff_filter` from `r2_run_store`.** It is a pure string builder for the shared claim filter (traceflow A6). R3 already depends on `R2RunStore` for its input, and a copy could drift from the one proven on the dev database.
- **D-R3-6, the two coordinators shut down concurrently.** `gather(r2.shutdown(), r3.shutdown())`. They share no task, and both must finish before the shared clients, the caller and the database close.

On accept, this plan is also saved as `backend/src/services/deep_search/feature_context/R3_Independent_Service_Implementation_Plan.md` (not a build todo).

---

## Build checklist (todos, in order)

1. Capture the test baseline: `cd backend && python -m pytest tests src/services/deep_search/feature_tests -q`, and save the failure list to the scratchpad.
2. Migration `backend/supabase/migrations/20261109000000_create_r3_runs.sql` (R3-C5).
3. Migration `backend/supabase/migrations/20261109000100_create_r3_run_steps.sql` (R3-C5 Iteration 1, with `degraded`).
4. Contracts in `feature_schemas/schemas.py`: `R3RunStatus`, `R3StepId`, `R3StepStatus`, `R3StepRecord`, `R3RunRecord`, `R3RunView`.
5. Exceptions in `src/exceptions/deep_search.py`: `RunSupersededError`, `R3_PROVIDER_ERRORS`, `R3_STAGE_ERRORS`; widen the `RunStoreError` docstring to `r3_runs`.
6. Settings in `src/core/config.py` + `backend/.env.example`: `r3_stale_after_seconds` (1800), `r3_parallel_search_concurrency` (10), `r3_firecrawl_concurrency` (2), `r3_firecrawl_rate_per_minute` (10).
7. Gateway (`src/clients/mcp_tools.py`): `McpProviderLimits`, `create_mcp_provider_limits`; three optional `McpToolGateway` keywords; the app-wide slot in `_call_with_retry` / `_single_call` at the five call sites; `create_mcp_tool_gateway(settings, *, limits=None)`.
8. R3 service (`specific_metric_resolution.py`): `resume_after` + `on_step_completed` on `run_specific_metric_resolution`; `provider_limits` on `create_specific_metric_resolution`.
9. New `r3_run_store.py`: state/output/step codecs (tuple keys, D-R3-1) + run-row and step-row operations.
10. New `r3_run_coordinator.py`: start/retry/status, live-run dict, execute, callback, checkpoint/finish/fail/step rows, retryable split, `is_config_error`, shutdown.
11. HTTP: `src/schemas/specific_metric_resolution.py`, `src/app/api/controllers/specific_metric_resolution.py`, `src/app/api/routes/specific_metric_resolution.py`, `get_r3_run_coordinator` in `dependencies/deep_search.py`, and wiring + Swagger tag + shutdown order in `src/app/main.py`.
12. New tests `tests/services/deep_search/test_r3_run_lifecycle.py` (fakes) + app-wide limit tests in `feature_tests/test_c3_1_1_mcp_tool_gateway.py`.
13. New live sample runner `feature_sample_runs/r3_run_lifecycle_sample_run.py`.
14. Run the suite and compare with the baseline (none new); run the sample runner (needs keys); fix whatever fails.

---

## 1. File and Module Structure

| File | Change | Owns |
|---|---|---|
| `backend/supabase/migrations/20261109000000_create_r3_runs.sql` | new | `r3_runs` DDL, `user_id` index, RLS on, `updated_at` trigger, output CHECK |
| `backend/supabase/migrations/20261109000100_create_r3_run_steps.sql` | new | `r3_run_steps` DDL, the two checks (with `degraded`), completed-immutable trigger |
| `backend/src/services/deep_search/feature_schemas/schemas.py` | modify | R3 run contracts (status, step ids, records, view) |
| `backend/src/exceptions/deep_search.py` | modify | `RunSupersededError`, `R3_PROVIDER_ERRORS`, `R3_STAGE_ERRORS` |
| `backend/src/core/config.py`, `backend/.env.example` | modify | the four R3 settings |
| `backend/src/clients/mcp_tools.py` | modify | `McpProviderLimits`, app-wide slots, limiter injection; no logic change |
| `backend/src/services/deep_search/specific_metric_resolution.py` | modify | `resume_after`, `on_step_completed`, factory `provider_limits` |
| `backend/src/services/deep_search/r3_run_store.py` | new | the only R3 module that knows Supabase: codecs + row operations |
| `backend/src/services/deep_search/r3_run_coordinator.py` | new | R3 run lifecycle: tasks, callback, fence, claim, retryable split, status |
| `backend/src/schemas/specific_metric_resolution.py` | new | `StartSpecificMetricResolutionRequest`, `ResolutionResultEntry`, run response |
| `backend/src/app/api/controllers/specific_metric_resolution.py` | new | view/typed error → status code + body |
| `backend/src/app/api/routes/specific_metric_resolution.py` | new | three route declarations + Swagger `responses` |
| `backend/src/app/api/dependencies/deep_search.py` | modify | `get_r3_run_coordinator` (503 when unconfigured) |
| `backend/src/app/main.py` | modify | composition root: limits, factory, store, coordinator, `r3_tasks`, shutdown order |
| `backend/tests/services/deep_search/test_r3_run_lifecycle.py` | new | fake service, fake R3 store, fake R2 output; R3-C9 fake rows |
| `backend/src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py` | modify | app-wide limit tests (existing harness) |
| `backend/src/services/deep_search/feature_sample_runs/r3_run_lifecycle_sample_run.py` | new | live retry of a run that failed in STEP 4 after its STEP 3 checkpoint |

No other new modules. The store and the coordinator own every new concern, as R1's and R2's do. The live-run entry, the execution identity and the progress tracker are small private dataclasses inside the coordinator module.

---

## 2. Contracts, Blueprint and Runtime Journey

### A. Feature Map

```
Feature: Deep Search
└─ Responsibility: SpecificMetricResolution (R3) — resolve specific metrics per amenity (unchanged logic)
   └─ Workflow: run_specific_metric_resolution(state, resume_after, on_step_completed)
      ├─ Stage: gateway open + catalog (unchanged)
      ├─ Stage: STEP 1 _build_plan_index · STEP 2 _derive_work_items (unchanged, recomputed)
      ├─ Stage: STEP 3 _run_discovery_batch — skipped when resume_after = discovery_batch
      ├─ Stage: R3-C3 barrier callback — on_step_completed("discovery_batch", state, breaker.open)
      ├─ Stage: STEP 4 _run_amenity_pipelines · STEP 5 sweep + run-level raise (unchanged)
      └─ Stage: finally gateway aclose (unchanged)
└─ Provider limits (R3-C2 Iteration 1): McpProviderLimits — app-wide Parallel / Firecrawl slots + rate
   └─ McpToolGateway._single_call — rate token → run slot → app-wide slot → timeout → call
└─ Run lifecycle: R3RunCoordinator — start / retry / status around the store
   ├─ R3-C7 E1 Start workflow: start_run
   │  ├─ R2RunStore.get_finished_output — R2's handoff (404 on missing / version)
   │  ├─ create row — r3_runs running, attempts 0
   │  └─ _schedule — run_id_var, task, live-run entry, 202
   ├─ R3-C6 E2 Retry workflow: retry_run
   │  ├─ _load_for_action — load + version check
   │  ├─ _precheck_retry — fast reject
   │  ├─ claim — one conditional update (the guard)
   │  ├─ _claim_resume_steps — failed / degraded rows → started
   │  └─ _schedule — resumed task, 202
   ├─ R3-C7 Iteration 2 E3 Status workflow: get_run
   │  ├─ live-run check (no I/O, carries completed_step)
   │  └─ _view — row → view
   ├─ Background execution: _execute
   │  ├─ per-run R3 instance from the factory (R3-C2)
   │  ├─ _on_step_completed — the R3-C3 callback: checkpoint or degraded flag
   │  ├─ _save_checkpoint (SAVE, FENCE) · _save_finished (FENCE) · _save_failed (FENCE)
   │  └─ _record_step / _record_degraded / _record_failed_step — step rows after a matched run write
   ├─ Retryable split: _retryable_for + is_config_error (R3-C7 Iteration 1)
   └─ shutdown — cancel + await live tasks (10 s)
└─ Persistence: R3RunStore — r3_runs / r3_run_steps rows, tuple-key codecs
└─ HTTP: routes → controllers → coordinator
└─ (harness) test_r3_run_lifecycle.py, r3_run_lifecycle_sample_run.py — not in the request path
```

### B. Data Contracts

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
|---|---|---|---|---|
| `SpecificMetricResolutionState` | R3's state (exists, unchanged) | inputs from R2 + STEP 3 stores + `resolution_results` | **mutable**: STEP 3 and STEP 5 write it | coordinator → service, store |
| `R3RunStatus` | run status | `running` / `finished` / `failed` | n/a | store → coordinator |
| `R3StepId` | step-row ids | `discovery_batch` / `pipelines` | n/a | coordinator, store |
| `R3StepStatus` | step-row status | `started` / `completed` / `degraded` / `failed` | n/a | store |
| `R3StepRecord` | one decoded step row | `step_id` · `status` · `error_type` · `retryable` | immutable | store → coordinator |
| `R3RunRecord` | one decoded run row | `run_id` · `user_id` · `r2_run_id` · `status` · `state` · `completed_step` · `attempts` · `retryable` · `updated_at` · `output` · `failure_stage` · `steps` | immutable | `load_run` → coordinator |
| `R3RunView` | what the page sees | `run_id` · `status` · `completed_step` · `result: list[dict] \| None` (encoded, D-R3-4) · `retryable` | immutable | coordinator → controller |
| `McpProviderLimits` | the app-wide limits | `search_slots: Semaphore` · `firecrawl_slots: Semaphore` · `firecrawl_rate: _TokenBucket` | shared, built once | lifespan → factory → each gateway |
| `StepCompletedCallback` | the R3-C3 hook type | `(step: str, state, breaker_open: bool) -> Awaitable[None]` | n/a | coordinator → service |
| State envelope | stored `state` | `{"version": R3_STATE_SCHEMA_VERSION, "state": {...}}`; tuple-keyed dicts as lists of `{category_id, place_id, value}` | n/a | store codec |
| Output envelope | stored `output` | `{"version", "output": [ {category_id, place_id, value: AmenityResolutionRecord} ]}` | n/a | store codec |
| Step envelope | stored step `output` | `{"schema_version", "data"}`: STEP 3's three dicts (discovery_batch), `resolution_results` (pipelines) | n/a | store codec |
| `StartSpecificMetricResolutionRequest` | E1 body | `r2_run_id: UUID` · extra forbidden | immutable | FastAPI → controller |
| `ResolutionResultEntry` | one result row | `category_id: int` · `place_id: str` · `value: dict` | immutable | controller |
| `SpecificMetricResolutionRunResponse` | E1/E2/E3 body | `run_id` · `status` · `completed_step?` · `result?: list[ResolutionResultEntry]` · `retryable?` | immutable | controller |
| Error body | every error | R1's `RunErrorResponse` reused: `error`, `run_id?`, `status?`, `retryable` (always when failed) | immutable | controller |

Rules surfaced: `completed_step` stays null until a clean STEP 3 checkpoint, and a `degraded` row never moves it. `output` is non-null iff `finished` (database CHECK). "Save as failed" never writes `state` or `completed_step`. Step-row `output` is non-null iff `completed` or `degraded`. `state`, `output` and step payloads share one tuple-key encoding.

**Columns** (`r3_runs`): `run_id uuid pk`, `user_id` → `auth.users` cascade, `r2_run_id` → `r2_runs` cascade, `status` check, `state jsonb not null`, `completed_step text` check `in ('discovery_batch')` or null, `output jsonb`, `failure_stage`, `failure_message`, `retryable bool not null default false`, `attempts int >= 0`, `created_at`, `updated_at` (trigger, `clock_timestamp()`), CHECK output iff finished. `r3_run_steps`: as `r2_run_steps`, with `step_id in ('discovery_batch','pipelines')`, `status in ('started','completed','degraded','failed')`, CHECK `(status in ('completed','degraded')) = (output is not null)`, CHECK failed iff error, PK `(run_id, step_id)`, completed-immutable trigger.

### C. Supporting Actors & Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
|---|---|---|---|---|
| `SpecificMetricResolution` | existing service, per run | `run_specific_metric_resolution(state, *, resume_after, on_step_completed)`, `aclose()` | one (tests: real class on a fake gateway, or a duck-typed scripted fake) | coordinator |
| Service factory | zero-arg callable | `() -> SpecificMetricResolution` | `functools.partial(create_specific_metric_resolution, ...)` | coordinator (D-R3-3) |
| `McpToolGateway` | existing client, per run | `open`, `search_web`, `map_site`, `scrape_page(s)`, `crawl_site`, `aclose` | one | R3 instance |
| `McpProviderLimits` | shared limit bundle | three fields, no methods | one, built in `lifespan` | every gateway |
| `R2RunStore.get_finished_output` | existing store method | `(run_id, user_id) -> AmenitySearchOutput \| None [raises: StateVersionMismatchError, RunStoreError]` | one | `start_run` |
| `R3RunStore` | concrete store | §D | one (tests duck-type a fake) | coordinator |
| Supabase `AsyncClient` | existing, service role, 10 s timeout | PostgREST builders | one | all stores |
| `StructuredLLMCaller` | existing, shared | used inside R3 | one | every R3 instance |

### D. Class & Method Blueprint

**`McpToolGateway`** (`mcp_tools.py`, constructor + call slot only)
| Method | Signature | Purpose (one line) |
|---|---|---|
| `__init__` | `(..., *, global_search_semaphore: Semaphore \| None = None, global_firecrawl_semaphore: Semaphore \| None = None, firecrawl_rate_limiter: _TokenBucket \| None = None)` | adds app-wide slots; a given limiter replaces its own bucket |
| `_call_with_retry` / `_single_call` | existing + `global_semaphore: Semaphore \| None = None` | take run slot, then app-wide slot, around each attempt |
| `create_mcp_provider_limits` | `(settings: Settings) -> McpProviderLimits` | build the three app-wide objects once from settings |
| `create_mcp_tool_gateway` | `(settings, *, limits: McpProviderLimits \| None = None) -> McpToolGateway` | pass the limits into the three keywords |

**`SpecificMetricResolution`** (modified entry + factory only)
| Method | Signature | Purpose (one line) |
|---|---|---|
| `run_specific_metric_resolution` | `(state, *, resume_after: Literal["discovery_batch"] \| None = None, on_step_completed: StepCompletedCallback \| None = None) -> state [mutates: state.*]` | skip STEP 3 on resume; await the callback at STEP 3's barrier |
| `create_specific_metric_resolution` | `(settings, *, llm_caller=None, provider_limits: McpProviderLimits \| None = None)` | build one instance on a new gateway with the shared limits |

**`R3RunStore`** (new, `r3_run_store.py`)
| Method | Signature | Purpose (one line) |
|---|---|---|
| `dump_state` / `load_state` | `(state) -> dict` / `(dict) -> state [raises: StateVersionMismatchError]` | versioned envelope; tuple-keyed dicts as entry lists |
| `dump_output` / `load_output` | `(results: dict[tuple,ARR]) -> dict` / `(dict) -> dict[tuple,ARR]` | versioned output envelope, same encoding |
| `dump_resolution_entries` | `(results) -> list[dict]` (module function) | JSON-ready result rows for the status view |
| `dump_step_output` / `load_step_output` | `(step_id, data) -> dict` / `(step_id, dict) -> Any` | step envelope for STEP 3 dicts or results |
| `create_run` | `(run_id, user_id, r2_run_id, state) -> None [raises: RunStoreError]` | insert `running`, attempts 0, no checkpoint |
| `save_checkpoint` | `(run_id, user_id, *, attempts, state) -> bool` | write state + `completed_step=discovery_batch`, fenced |
| `save_finished` | `(run_id, user_id, *, attempts, state, output) -> bool` | `finished`, state, output, `retryable=false`, failure fields null, fenced |
| `save_failed` | `(run_id, user_id, *, attempts, stage, message, retryable) -> bool` | `failed` + failure columns, fenced; never touches state |
| `claim_retry` | `(run_id, user_id, *, expected_attempts, stale_before) -> bool` | the one-statement claim (R3-C6) |
| `mark_version_mismatch` | `(run_id, user_id) -> None` | failed, not retryable, stage `load_state`, unless finished |
| `load_run` | `(run_id, user_id) -> R3RunRecord \| None [raises: StateVersionMismatchError, RunStoreError]` | one read with step rows embedded; fails loudly without them |
| `insert_step` | `(run_id, step_id, data) -> bool` | new `completed` row; False on duplicate |
| `complete_claimed_step` | `(run_id, step_id, data) -> bool` | `started → completed` with output |
| `save_step_degraded` | `(run_id, step_id, data, *, claimed: bool) -> bool` | new `degraded` row, or `started → degraded` |
| `save_step_failed` | `(run_id, step_id, *, error_type, message, retryable, claimed) -> bool` | new `failed` row, or `started → failed` |
| `claim_step` | `(run_id, step_id) -> bool` | `failed`/`degraded` → `started`, error and output cleared |
| `_execute` | `(operation, query, *, conflict_ok=False) -> list[dict] [raises: RunStoreError]` | as R2: SDK/transport error → typed error + one log line |

**`R3RunCoordinator`** (new, `r3_run_coordinator.py`). Module constants: `MAX_RETRY_ATTEMPTS = 1`, `DEFAULT_STALE_AFTER_SECONDS = 1800`, `R3_SHUTDOWN_TIMEOUT_SECONDS = 10`, `CHECKPOINT_STEP = "discovery_batch"`, `_SETUP_ERRORS = (McpConnectionError, McpToolUnavailableError, MetricResolutionValidationError)`.
| Method | Signature | Purpose (one line) |
|---|---|---|
| `__init__` | `(store, r2_store, *, service_factory, stale_after_seconds=1800)` | holds the store, R2 reader, factory and live-run dict |
| `tasks` | property `-> dict[str, _LiveRun]` | the live dict (`app.state.r3_tasks` is this object) |
| `start_run` | `(user_id, r2_run_id) -> R3RunView [raises: RunNotFoundError, RunStoreError]` | read R2's output, create the row, schedule, `running` view |
| `retry_run` | `(user_id, run_id) -> R3RunView [raises: RunNotFoundError, RunConflictError, RunStoreError]` | load, pre-check, claim run, claim step rows, schedule resume |
| `get_run` | `(user_id, run_id) -> R3RunView [raises: RunNotFoundError, RunStoreError]` | live entry first, then the read-only row view |
| `shutdown` | `(timeout_seconds=10) -> None` | cancel live tasks, await them, log what is left |
| `is_config_error` | `(exc) -> int \| None` (module function) | the 401/403 behind `McpConnectionError`, via cause and groups |
| `_schedule` | `(execution, state, resume_after) -> None [mutates: self._tasks]` | set `run_id_var`, create task, add entry, done callback |
| `_on_task_done` | `(execution, task) -> None [mutates: self._tasks]` | remove only its own entry; log a crashed task |
| `_execute` | `(execution, state, resume_after) -> None` | run R3 once, then exactly one terminal write (or none on lost fence) |
| `_on_step_completed` | `(execution, progress) -> StepCompletedCallback` | build the callback: checkpoint, or set the degraded flag |
| `_save_checkpoint` | `(execution, state) -> None [raises: RunSupersededError, RunStoreError]` | fenced checkpoint, then the `discovery_batch` row, then the live entry |
| `_save_finished` | `(execution, state, progress) -> None` | fenced finish, then `pipelines` row and any degraded row |
| `_save_failed` | `(execution, exc, progress) -> None` | fenced fail write, then failed + degraded rows; never raises |
| `_record_step` | `(execution, step_id, data) -> None [raises: RunSupersededError]` | insert or complete-claimed; conflict stops, store error only logs |
| `_record_degraded` | `(execution, state) -> None` | write STEP 3's data as a `degraded` row |
| `_retryable_for` | `(exc, attempts) -> tuple[stage, retryable, config_status]` | the R3-C7 table |
| `_load_for_action` | `(user_id, run_id) -> R3RunRecord [raises: RunNotFoundError, RunConflictError]` | load; version mismatch → mark row, `409` |
| `_precheck_retry` | `(record) -> None [raises: RunConflictError]` | finished / not retryable / limit used / alive → `409` |
| `_claim_resume_steps` | `(record, attempts) -> frozenset[R3StepId] [raises: RunConflictError]` | claim every failed/degraded row from the resume step on |
| `_is_stale` | `(record) -> bool [raises: RunStoreError]` | `running` and `updated_at` older than `stale_after` |
| `_view` | `(record) -> R3RunView` | row → view by status (result encoded) |

Private: `_Execution` (frozen: `run_id, user_id, attempts, claimed_steps: frozenset, path`), `_Progress` (mutable, one per execution: `in_flight: R3StepId \| None`, `step3_degraded: bool`), `_LiveRun` (mutable: `task, user_id, completed_step`).

**Controllers** (`controllers/specific_metric_resolution.py`): `start_run(body, user, coordinator) -> 202`, `retry_run(run_id, user, coordinator) -> 202`, `get_run(run_id, user, coordinator) -> 200`, `_error_response(exc, *, not_found)`: `RunNotFoundError` → 404, `RunConflictError` → 409 with `run_id/status/retryable`, `RunStoreError` → 503, anything else re-raised (500).

**Routes** (`routes/specific_metric_resolution.py`): prefix `/api/specific-metric-resolution/runs`, router-level `Depends(get_authenticated_user)`, `POST ""`, `POST "/{run_id}/retry"`, `GET "/{run_id}"`, each with only its statuses. Reuses `_UNAUTHENTICATED`, `_STORE_UNAVAILABLE` from the R1 routes module.

### E. Runtime Flow: Data Object Journey

**E1 start (request part, milliseconds)**
| # | Stage | Reads | Produces / mutates | Shape after |
|---|---|---|---|---|
| 1 | request model | JSON body | `StartSpecificMetricResolutionRequest` or `422` | `r2_run_id` |
| 2 | `R2RunStore.get_finished_output` | `r2_run_id`, `user_id` | `AmenitySearchOutput` or `404` / `503` | R2 handoff |
| 3 | build state | handoff | `SpecificMetricResolutionState` | inputs set, outputs empty |
| 4 | `R3RunStore.create_run` | new `run_id`, state | row `running`, attempts 0 | row exists |
| 5 | `_schedule` | `_execute(attempts=0, resume_after=None)` | `tasks[run_id] = _LiveRun(task, user, None)` | `202 {run_id, status: running}` |

**Background (`_execute`, minutes)**
| # | Stage | Reads | Produces / mutates | Shape after |
|---|---|---|---|---|
| 6 | factory | — | per-run R3 instance, new gateway on app-wide limits | instance ready |
| 7 | gateway open, STEP 1, STEP 2, catalog | state inputs | work items (not stored) | unchanged state |
| 8 | STEP 3 (skipped on resume) | work items | `[mutates: state.official_gate_results, discovery_search_results, website_search_results]` | verdict per item |
| 9 | callback, breaker closed | state | row `completed_step=discovery_batch`; `discovery_batch` row completed; live entry step | checkpoint saved |
| 9' | callback, breaker open | — | `progress.step3_degraded = true`; no write | null checkpoint |
| 10 | STEP 4 + STEP 5 | verdicts, records | `[mutates: state.resolution_results]`, or run-level raise | records per item |
| 11 | `_save_finished` | final state | row `finished` + output; `pipelines` completed; `degraded` row if 9' | finished |
| 11' | `_save_failed` (any error at 6–11) | exception, progress | row `failed`, stage, `retryable`; in-flight failed row; degraded row if 9' | state untouched |
| 12 | `aclose` + done callback | — | gateway closed; entry removed after the save | not in memory |

**E2 retry**: `load_run` → `_precheck_retry` → `claim_retry` (attempts n → n+1) → `_claim_resume_steps` → `_schedule(resume_after=completed_step, claimed_steps)` → `202 {run_id, status: running, completed_step}`. The background then runs 6–12 with STEP 3 skipped when `completed_step = discovery_batch`, every write fenced on n+1.

**E3 status**: live entry (own → `running` + entry's `completed_step`; another user's → `404`) → `load_run` → `_view`.

**Transformation trace (shape only):**
```
StartSpecificMetricResolutionRequest{ r2_run_id }
 → AmenitySearchOutput{ plans, discovered_places, predefined_records }           # r2_runs.output
 → SpecificMetricResolutionState{ inputs }                                         # r3_runs.state v1, running
 → + official_gate_results / discovery_search_results / website_search_results     # SAVE completed_step=discovery_batch
     (breaker open: no save; degraded flag)
 → + resolution_results{(cat, place) → AmenityResolutionRecord}                    # r3_runs.output, finished
   | failed{ failure_stage, retryable }  (state and completed_step unchanged)
 → R3RunView{ status, completed_step, result[{category_id, place_id, value}] | retryable }
```

**Approach at the decision points**
- **Resume position:** `completed_step` alone decides it. Null → STEP 3 runs; `discovery_batch` → STEP 3 skipped. STEP 1, STEP 2 and the catalog are always recomputed.
- **The callback:** awaited inside the method's `try`. Breaker closed → checkpoint. Breaker open → flag only. A lost fence raises `RunSupersededError` and a store error raises `RunStoreError`; both leave through the method's `finally`, so the gateway closes.
- **In-flight step:** `discovery_batch` until the callback (or `pipelines` from the start on a resume). The callback sets `pipelines` in both branches. A `_SETUP_ERRORS` failure writes no step row.
- **The claim:** one UPDATE `SET status=running, attempts=n+1, retryable=false WHERE run_id AND user_id AND attempts=n AND ((failed AND retryable) OR (running AND updated_at < cutoff))`. Zero rows → `409` "Another retry of this run already started".
- **Step-row claim:** for the resume step and every later step (`discovery_batch` then `pipelines`, or only `pipelines`), a `failed` or `degraded` row → `claim_step`. A False → the run is saved failed, not retryable, and `409` "start again". No such row → nothing to claim.
- **Write order on every save:** run row (fenced) first. Zero rows → log `r3_run.superseded`, no step row. Step rows only after a match. Duplicate/moved → `r3_run.step_conflict`; step-row store error → WARN, carry on.
- **Retryable split** (`_retryable_for`; every "yes" is `attempts < 1`):

| Error | Stage | Retryable |
|---|---|---|
| `MetricResolutionProviderError` (`availability`, `circuit_open`, `content`) | `exc.stage` | yes |
| `McpConnectionError`, no 401/403 on its causes | `exc.stage` | yes |
| `McpConnectionError` with 401/403 on its causes | `exc.stage` | no, ERROR `r3_run.config_error` |
| `MetricResolutionValidationError`, `McpToolUnavailableError` | `exc.stage` | no |
| `RunStoreError` (checkpoint or finish write) | `run_store` | yes |
| `RunSupersededError` | — | not saved |
| `CancelledError` (shutdown) | `cancelled` | yes, then re-raise |
| anything else | `unexpected` | no, `logger.exception` |

### F. Method Detail

**`SpecificMetricResolution.run_specific_metric_resolution`** (modified)
- **What changes:** `_run_discovery_batch` runs only when `resume_after` is not `discovery_batch`. Right after it, the callback (if given) is awaited with `breaker.open`. Everything else in the method is byte-for-byte unchanged.
- **Defaults:** no arguments → today's behavior, so the existing R3 suites pass unchanged.

**`McpToolGateway._single_call`**
- Order: rate token (Firecrawl only, outside the timeout, as today) → run slot → app-wide slot (when given) → timeout → `call_tool`. The slots are held only across the live call, never across backoff sleeps (unchanged rule).
- Parallel calls pass `global_search_semaphore`; the four Firecrawl paths (map, scrape, crawl start, crawl status) pass `global_firecrawl_semaphore`.

**`R3RunCoordinator._execute`**
- Builds the instance, makes a `_Progress`, calls the method with `resume_after` and the callback, then `_save_finished`. `RunSupersededError` → stop (already logged). `CancelledError` → `_save_failed`, then re-raise. Any other exception → `_save_failed`. The `finally` awaits `instance.aclose()` (idempotent; shared caller not owned).

**`R3RunCoordinator._schedule` / `_on_task_done`**
- `run_id_var` is set before `create_task` and reset after, so the task context carries the run ID. The done callback removes the entry only if it still holds this task, and runs after the task's save. A non-cancel exception left the task → ERROR `r3_run.task_crashed`.

**`R3RunCoordinator.get_run`**
- Live entry first, no I/O. `StateVersionMismatchError` → `failed`, not retryable, WARN `r3_run.status_degraded`, no write. `None` → `RunNotFoundError`. A stale `running` row still reads `running` (B5 is open).

**`R3RunCoordinator.shutdown`**
- Cancels every live task, `asyncio.wait(..., 10 s)`. Each task's method `finally` closes its gateway, then the task saves itself failed. Pending tasks → WARN `r3_run.shutdown_timeout` with their run IDs.

**`is_config_error`**
- Walks from the `McpConnectionError`: `__cause__`, plus the members of an exception group, at most 8 levels deep. Each link is checked for `status_code` or `response.status_code` in {401, 403}. The first hit is returned; none → None.

**`R3RunStore` state codec**
- Non-tuple fields: per-field `TypeAdapter` dump/validate (as R2's). The four tuple-keyed dicts: lists of `{category_id, place_id, value}` in insertion order, rebuilt in the same order.
- Every `AmenityResolutionRecord` with a `phase1`: `_index` written as `{}` and rebuilt from `items` on load (D-R3-1).

---

## 3. Async Structure

| Layer / group | Operations and I/O | Data dependency | Placement | Ordering |
|---|---|---|---|---|
| HTTP route → controller → coordinator | one coroutine per request | n/a | event loop | awaited |
| E1 request part | `get_finished_output` → `create_run` → `create_task` | the row needs the handoff; the task needs the row | event loop (async PostgREST) | sequential |
| E2 request part | `load_run` → `claim_retry` → `claim_step` (0 to 2) → `create_task` | step claims are valid only after the run claim wins | event loop | sequential (step claims too: a False stops the retry) |
| E3 | dict lookup (no I/O) → `load_run` | the read only happens on a miss | event loop | sequential |
| Background task, step level | open → STEP 1/2 → STEP 3 → callback write → STEP 4 → STEP 5 → final write → step rows | each reads the previous output; the checkpoint lands before STEP 4's spend | event loop, one task per run | sequential |
| Inside STEP 3 / STEP 4 | discovery fan-out, amenity pipelines, phase-1 searches | independent per item (unchanged) | event loop | concurrent via `gather` (unchanged), each web call bounded by run slot then app-wide slot |
| Final write → step rows | run-row UPDATE → `pipelines` row → degraded row | step rows follow a matched run write; the two step rows are independent | event loop | sequential (two small writes; overlap saves nothing measurable) |
| Different runs | separate tasks | independent | event loop | concurrent; share only the app-wide limits |
| Shutdown | `gather(r2.shutdown(), r3.shutdown())` → close clients, caller, database | the closes need every task's failed write done | event loop | concurrent shutdowns (D-R3-6), then sequential closes |

**Blocking check:** no blocking I/O. MCP and LLM clients are async, Supabase is the async client with a 10 s PostgREST timeout. The state codec is CPU work on the event-loop thread (the loop's single thread). R3's state holds evidence text for every amenity, so `r3_run.checkpoint_saved` and `r3_run.finished` log `state_chars`. At MVP sizes (a few places per category) this runs in milliseconds and stays inline. Moving it to a thread is reserved until a logged size shows it holding the loop (drift rule 1: observe before guarding).

**Shared state:** each task owns its own state, R3 instance, gateway and breaker (one-object model per run). The shared mutable objects are the live-run dict (touched only on the loop thread by `_schedule`, the callback and the done callback) and the three app-wide limits (built to be shared; the token bucket has its own lock).

---

## 4. Drift Entries (per method)

**`R3RunCoordinator.start_run`**
- **Core behavior:** read R2's finished output, create the row, schedule the task.
- **Drifts handled:**
  - **Body not a UUID or carries extra fields.** Caught at the **edge** (request model, `extra="forbid"`). **Rejected** `422`, no row.
  - **R2 run missing, another user's, unfinished, or another output version.** **Core** (`get_finished_output` returns None or raises `StateVersionMismatchError`). **Rejected** `404`, logged `r3_run.rejected` with `reason`, no row.
  - **Database down before the row.** **Infra** (store). **Propagated** `RunStoreError` → `503`, no row.
- **Left out (why):**
  - Deduplicating two starts for one R2 run: left out on purpose by the spec. *Not live.*
  - Checking that the handoff has eligible categories: zero work items is a valid run (STEP 3 on an empty list, saved). *Trust.*

**`R3RunCoordinator.retry_run`**
- **Core behavior:** claim once, claim step rows, resume after `completed_step`.
- **Drifts handled:**
  - **Two retries at once.** **Infra** (one conditional UPDATE). **Rejected** `409` for the loser, nothing scheduled.
  - **Run still alive.** **Core** (`_precheck_retry`, `_is_stale`, 30 min). **Rejected** `409 status: running`.
  - **Finished, not retryable, or limit used.** **Core**. **Rejected** `409`.
  - **Saved under another version.** **Core** (`_load_for_action`). **Rejected**: row marked failed, not retryable, `409`.
  - **A failed/degraded step row moved after the run claim won.** **Core**. **Rejected**: run saved failed, not retryable, `409` "start again".
  - **Step rows missing from the embedded read.** **Infra** (`load_run`). **Rejected** `RunStoreError` → `503`, never "no steps".
- **Left out (why):**
  - A `started` row on a stale reclaim: a `started` row only exists after a claim (attempts ≥ 1), and a reclaim needs attempts 0. *Not live.*
  - A resume step whose row is already `completed`: `discovery_batch` completes only with the checkpoint, and `pipelines` only after the finish write. *Not live.*

**`R3RunCoordinator._execute` (with the callback)**
- **Core behavior:** run R3 once and settle the row exactly once.
- **Drifts handled:**
  - **Breaker open at the end of STEP 3.** **Core** (callback's `breaker_open`). **Recover-degrade**: no checkpoint, `step3_degraded` set, WARN `r3_run.step3_degraded` (the only signal that a retry will rerun STEP 3).
  - **A provider, gateway or catalog error.** **Core** (`_retryable_for`). **Reject** to the row: `failed`, retryable per the table.
  - **A refused web-provider key.** **Core** (`is_config_error`). **Reject**: not retryable, ERROR `r3_run.config_error`.
  - **Shutdown cancels the task.** **Core**. **Recover**: saved failed, `retryable = attempts < 1`, re-raised.
  - **A newer execution owns the row** (lost fence at the checkpoint). **Infra** (the `attempts` filter). **Stop**: `RunSupersededError` through the method's `finally`, INFO `r3_run.superseded`, no further writes.
  - **The checkpoint write itself fails.** **Infra**. **Reject**: `RunStoreError` leaves through the `finally`, saved with stage `run_store`, retryable.
- **Left out (why):**
  - Per-item `none` verdicts below the breaker threshold: kept as real results by today's logic (B12, open in the spec). *Not decided here.*
  - A timeout around a whole step: every web call has its own timeout and bounded retries, and LLM calls have the provider chain. *Wrong boundary.*
  - Re-validating the loaded state: the codec rebuilds the exact saved types. *Trust.*

**`R3RunCoordinator._save_finished` / `_save_failed` / step-row writers**
- **Core behavior:** one fenced run-row write, then the step rows.
- **Drifts handled:**
  - **Database error on the finish write.** **Infra**. → `_save_failed` with stage `run_store`. If that write fails too: ERROR `r3_run.failed_not_saved`; the row stays `running` and is reclaimable after 30 min.
  - **Step row duplicate or moved.** **Infra** (PK `23505` / status filter). **Stop**, INFO `r3_run.step_conflict`.
  - **Step-row store error.** **Infra**. **Recover-degrade**: WARN `r3_run.step_record_failed`, the run row stands.
- **Left out (why):**
  - A transaction across both tables: PostgREST has none, and the write order keeps the run row right. *Accepted (R3-C5 Iteration 1).*
  - Retrying a failed write: unsafe without knowing whether it landed; the stale reclaim covers it. *Trust.*
  - A `degraded` row lost in a hard crash after STEP 3: record only (B29). *Accepted.*

**`R3RunCoordinator.get_run`**
- **Core behavior:** read-only status.
- **Drifts handled:**
  - **Another user's live task.** **Core** (the entry keeps `user_id`). **Reject** `404`.
  - **The memory reply shows a step the row doesn't have.** **Core**: the entry's `completed_step` is set only after the checkpoint write matched.
  - **Version mismatch.** **Core**. **Degrade**: `failed`, not retryable, WARN `r3_run.status_degraded`, no write.
  - **Database down.** **Infra**. **Propagate** `503`.
- **Left out (why):**
  - A stale `running` row reported as retryable: B5 left open by the spec. *Not decided here.*
  - A run live in another worker: falls through to the row read (B28). *Not live at one process.*

**`R3RunCoordinator.shutdown`**
- **Core behavior:** cancel and await live tasks before shared resources close.
- **Drifts handled:**
  - **A task's gateway close plus failed write outlasts 10 s.** **Infra**. **Degrade**: WARN `r3_run.shutdown_timeout` with pending run IDs; rows stay `running`, reclaimable.
- **Left out (why):**
  - New starts during shutdown: uvicorn stops accepting requests before lifespan teardown. *Not live.*

**`is_config_error`**
- **Core behavior:** find a 401/403 behind `McpConnectionError`.
- **Drifts handled:**
  - **A cause cycle or deep group nesting.** **Core**: depth limit 8.
- **Left out (why):**
  - Other status shapes (text-only 401 messages): the real hosted shape is unconfirmed (B26). *Unknown: confirm with the live wrong-key run, not a guard.*
  - A refused LLM key: the cause is gone by STEP 5 (B25). *Out of scope, risk accepted.*

**`R3RunStore` codecs and `load_run`**
- **Core behavior:** exact round trip of state, output and step payloads.
- **Drifts handled:**
  - **Tuple keys in the four state dicts.** **Core** (entry lists). Proven failing today without it.
  - **Tuple keys inside `MetricsSourceContent._index`.** **Core** (D-R3-1). Proven failing in the planning scratch run.
  - **`place_id` containing `,`.** **Core**: keys are never joined into strings.
  - **Version differs.** **Core**. **Reject** `StateVersionMismatchError`.
  - **Embed missing; `updated_at` not ISO.** **Infra**. **Reject** `RunStoreError` (loud, never "no steps" or "not stale").
- **Left out (why):**
  - Payload size limits: a few places per category, well under PostgREST limits; sizes are logged (`state_chars`). *Observe first.*

**`R3RunStore.claim_retry`**
- **Core behavior:** the single winner of a retry.
- **Drifts handled:**
  - **Timestamp format in the OR filter.** **Infra**: the shared `stale_cutoff_filter` (D-R3-5). A malformed filter is a loud `APIError` → `503`.
- **Left out (why):**
  - A different filter for R3: same statement as R2's, already checked on the dev database. *Not live.*

**`McpToolGateway._single_call` (app-wide slot)**
- **Core behavior:** run slot, then app-wide slot, per call.
- **Drifts handled:**
  - **Runs hoarding app-wide slots.** **Core**: the enter order means a run waiting on its own limit holds no app-wide slot.
  - **A slot wait counted as call time.** **Core**: both slots are taken outside the per-call timeout (unchanged rule).
- **Left out (why):**
  - An app-wide LLM cap: the spec leaves it out. *Decided by spec.*
  - Multi-worker limits: one process at MVP (B20). *Accepted.*

**`SpecificMetricResolution.run_specific_metric_resolution` (resume)**
- **Core behavior:** today's behavior, plus skip-and-hook.
- **Drifts handled:**
  - **Resume with STEP 3 outputs missing from the state.** **Core**: the existing `missing_verdict` WARN de-masks it per item (unchanged code).
- **Left out (why):**
  - Carrying the breaker across attempts: a fresh breaker per execution (R3-C3). *Decided by spec.*

---

## 5. Log Plan

All lines are JSON on `DEEP_SEARCH_LOGGER_NAME`, carry `run_id` (`run_id_var`, set before `create_task`) and `user_id`. R3's own stage lines (`r3m1_3.*`, `r3m1_4.*`, `r3m1_5.*`, `metric_resolution.*`) are unchanged and pick up `run_id` from the same context variable.

| Event | Level | Node type | Driving state |
|---|---|---|---|
| `r3_run.created` | INFO | state change | `r2_run_id`, `work_categories`, `place_count`, `schema_version` |
| `r3_run.rejected` | INFO | boundary (reject handled) | `reason` (r2_not_found, r2_version_mismatch, not_found, finished, not_retryable, still_running, cas_lost, step_conflict, version_mismatch), `status` |
| `r3_run.loaded` | INFO | boundary (database in) | `status`, `attempts`, `completed_step`, `retryable`, `step_statuses` |
| `r3_run.retry_started` | INFO | state change | `attempts`, `resume_after`, `claimed_steps`, `reclaimed_stale` |
| `r3_run.checkpoint_saved` | INFO | state change | `attempts`, `verdict_counts` (google/discovered/none), `state_chars` |
| `r3_run.step3_degraded` | WARN | silent drift | `attempts`, `work_items` |
| `r3_run.finished` | INFO | state change | `attempts`, `outcome_counts`, `path`, `state_chars` |
| `r3_step.saved` | INFO | state change | `step_id`, `status`, `path` (insert / claimed) |
| `r3_run.failed` | ERROR | endpoint | `stage`, `step_id`, `error_class`, `retryable`, `attempts`, `saved`, `message` |
| `r3_run.config_error` | ERROR | endpoint detail | `step_id`, `http_status`, `error_class` |
| `r3_run.superseded` | INFO | boundary (fence lost) | `operation`, `attempts` |
| `r3_run.step_conflict` | INFO | boundary (reject) | `step_id`, `path` |
| `r3_run.step_record_failed` | WARN | silent drift | `step_id`, `operation`, `store_error` |
| `r3_run.failed_not_saved` | ERROR | silent drift | `stage`, `store_error` |
| `r3_run.status_degraded` | WARN | silent drift | `found_version`, `expected_version` |
| `r3_run.shutdown_timeout` | WARN | silent drift | `pending_run_ids`, `timeout_seconds` |
| `r3_run.task_crashed` | ERROR | endpoint | `error_class`, `detail` |
| `r3_run.store_error` | ERROR | boundary (database out) | `operation`, `error_class`, `detail` |

No line per memory-check hit (polling would flood the log), per slot wait, or per skipped STEP 3: the skip is deterministic from `retry_started.resume_after`.

---

## 6. Sample Runner and Fixture Set

### 6.1 Live sample runner: `feature_sample_runs/r3_run_lifecycle_sample_run.py` (new)

**How to run it:** from `backend/` (needs `OPENAI_API_KEY` and/or `GROQ_API_KEY`, the Parallel/Firecrawl MCP settings and network; no Supabase):

```bash
python -m src.services.deep_search.feature_sample_runs.r3_run_lifecycle_sample_run
```

**What it seeds** (the handoff as R3.M1.3 leaves it; no earlier mechanism is called, and STEP 3 is skipped by the resume):
- An in-memory row holder with `R3RunStore`'s method names, the same fence and claim rules, and the real codecs, so every payload round-trips through JSON as the database would.
- One `r3_runs` row that **failed in STEP 4 after its STEP 3 checkpoint**: `status=failed`, `retryable=true`, `attempts=0`, `completed_step="discovery_batch"`, `failure_stage="run_specific_metric_resolution"`. Plus a `completed` `discovery_batch` step row and a `failed` `pipelines` step row.
- Its state: two real places from the M1.1 capture (`data/m1_1_discovered_places.json`), each with a `PredefinedMetricsRecord` built from its captured name, address and website:
  - Brentanobad (category 0, `swimming_pool`, `specific_attributes`): metrics `heated_pool_water` (factual, boolean) and `summer_weekend_crowding` (experiential), plus two fictional Places-shape reviews about crowding.
  - Bäckerei Schaan (category 1, `bakery`, `specific_attributes`): metrics `sourdough_bread_offered` (factual, boolean) and `saturday_morning_queue` (experiential), no reviews.
- STEP 3 outputs as the gate writes them: `website_search_results = google` for both captured websites, and the matching `official_gate_results`.
- Worked-pair rule: none of this reuses the R3 prompt worked pairs (Northgate Branch Library, Northside Bouldering Hall, Lantern Street Coworking Café) or the R3.M2.2 runner seed (Elmstead ice rink, Brackley allotments).

**What it drives:** the real `R3RunCoordinator.retry_run` with the real factory: a real gateway on real app-wide limits (Parallel 10, Firecrawl 2, 10/min), the real LLM caller. It awaits the scheduled task, then calls `get_run`. Live calls: STEP 4 only (phase-1 turns, Parallel searches, resolution turns), never STEP 3.

**What it prints, one titled section each:**
1. Settings and app-wide limits in use.
2. Seeded run row and step rows (status, attempts, `completed_step`, verdicts per amenity).
3. Pre-check and claim: attempts 0 → 1, `pipelines` step `failed → started`.
4. STEP 3 calls during the resume (must be 0, counted from `r3m1_3.discovery_batch_start` events).
5. STEP 4 trail: `r3m1_4.pipelines_start/done`, phase-1 turns, searches run, `llm_provider` attempt lines, `metric_resolution.done` per amenity.
6. Peak in-flight Parallel and Firecrawl calls, read from runner-side counting wrappers around the app-wide semaphores.
7. The finish write: row status, `output` and `state_chars`, step rows (`pipelines` now `completed` via the claimed path).
8. The status read: `R3RunView` with, per amenity, the outcome, kept labels with `final_value` and `basis`, and unresolved reasons.
9. The run's `r3_run.*` lifecycle lines in order.

**On a typed failure:** the failed row's `failure_stage` and `retryable`, the exception class and message, exit code 1. Nothing is written to Supabase or to disk.

### 6.2 Fixture set (pytest, no live calls)

**`tests/services/deep_search/test_r3_run_lifecycle.py`. Fakes:**
- `RoutingProvider` / `FakeGateway` in the style of `test_r3_m1_4_phase1_behavior_suite.py`, so the **real** `SpecificMetricResolution` runs through the factory (parity, resume, callback, breaker cases), with search-call counts per objective.
- `ScriptedService`: a duck-typed R3 for lifecycle-only cases (gate events, injected errors with real cause chains, a breaker-open callback).
- `FakeR3RunStore`: in-memory rows applying the SQL rules, each next to a comment naming the condition it copies: the `user_id` filter, the `running AND attempts=n` fence, the claim OR with a test clock, "save as failed never touches state", output iff finished, PK on step rows, completed-immutable, step output iff `completed`/`degraded`. Every payload round-trips through the real codecs and JSON.
- `FakeR2Output`: `get_finished_output` over in-memory R2 outputs, with a version-mismatch switch.

| Test | Passes when |
|---|---|
| default parity | `run_specific_metric_resolution(state)` with no new arguments matches the coordinator's finished state |
| resume parity | a STEP 4 failure then a retry gives the same final state as a clean run; STEP 3 searches made once in total |
| degraded STEP 3 | breaker open at STEP 3 → `completed_step` null, `degraded` `discovery_batch` row with data, `failed` `pipelines`; a retry reruns STEP 3, both rows `started` → `completed` |
| failed keeps checkpoint | save-as-failed leaves `state` and `completed_step` unchanged |
| round trip | initial, after-STEP-3 and finished states and the output come back equal, incl. a `,` in `place_id`, a real R2 output, and `_index` rebuilt to the same item objects |
| version mismatch | retry → `409`, row failed not retryable; status → `failed`, `retryable:false`, no write; start on an R2 version mismatch → `404` |
| concurrent retries | two `retry_run` calls gathered: one schedules, the other gets `409` |
| stale reclaim | a `running` row older than 30 min (test clock) is claimed; a fresh one gets `409 running`; a stale one at attempts 1 gets `409` |
| fencing | a write with an old `attempts` matches nothing and adds no step row; a lost checkpoint fence stops the method (gateway closed) |
| retry limit | a second failure after a retry is saved `retryable:false` |
| retryable split | each table row gives its stage / retryable; a `401` under `McpConnectionError` (incl. inside an exception group) → false + one `r3_run.config_error`; a timeout cause → true |
| database blip | a `RunStoreError` on the checkpoint saves stage `run_store`, retryable; the failed write failing too leaves `running` + `r3_run.failed_not_saved` |
| setup errors | a gateway-open or catalog failure writes no step row |
| step rows | clean run: `completed` `discovery_batch` + `pipelines`; a STEP 5 raise leaves no `completed` `pipelines` row |
| ownership | another user's run: start, retry and status all `404` |
| background lifecycle | start and retry return before STEP 1 (gate in the scripted service); `shutdown` mid-run saves `failed` + retryable before the fake caller and store close; the dict is empty after completion |
| status memory check | live task → `running` + entry `completed_step`, zero store reads; it changes only after the checkpoint write; another user → `404`; after the end → row read |
| HTTP | via `ASGITransport` with overrides: `401` without cookie on all three, `422` (bad UUID, extra field), `404`, `202` bodies, `409` bodies with `retryable`, `503` store down, `503` when R3 is not configured, finished `result` as `{category_id, place_id, value}` rows |

**Added to `feature_tests/test_c3_1_1_mcp_tool_gateway.py`** (existing fake-session harness):
| Test | Passes when |
|---|---|
| app-wide Parallel slots | two gateways sharing a semaphore of 10: in-flight searches never exceed 10, and never 4 per gateway |
| app-wide Firecrawl slots | two gateways sharing a semaphore of 2: in-flight Firecrawl calls never exceed 2 |
| providers kept apart | a full Firecrawl pool does not delay a Parallel call |
| shared limiter | a gateway given the limiter uses it, not its own bucket |
| defaults unchanged | no limits passed → today's behavior (the whole existing file passes unchanged) |

**Regression:** the existing R3 feature suites, the R2 and R1 suites pass; the failure list equals the baseline captured in todo 1.

---

## 7. Verification

1. `cd backend && python -m pytest tests src/services/deep_search/feature_tests -q`: §6.2 passes, and the failure list equals the baseline (none new).
2. `python -m src.services.deep_search.feature_sample_runs.r3_run_lifecycle_sample_run`: section 4 shows 0 STEP 3 calls, section 6 stays within 10 / 2, section 7 shows `finished` with the `pipelines` row `completed`, section 8 shows records.
3. **By hand on the dev database (R3-C9):** apply both migrations twice (no change the second time); RLS blocks the publishable key; the `updated_at` trigger moves on update; the completed-immutable trigger rejects a change; a `degraded` row accepts output and a `started` one doesn't; one `claim_retry` on a stale and a fresh row proves the OR filter.
4. **Manual HTTP (Swagger):** finish an R2 run → `POST /api/specific-metric-resolution/runs` → `202`; poll `GET` → `running` (`completed_step` null → `discovery_batch`) → `finished` with `result`; a wrong Firecrawl key → `failed`, `retryable:false` (B26 check); `POST .../retry` on a retryable failure → `202` with no `r3m1_3.*` lines in the log.

---

## 8. Architecture & Modularity Decisions

### Layer 1: Glance

- **Shape:** a concrete run coordinator runs R3's one unchanged entry method, once per execution, in a background task. It builds a fresh R3 instance per run from a factory, saves at STEP 3's barrier through a callback, and writes through a concrete Supabase store. Every per-run gateway shares one app-wide limit per web provider.
- **Seams:**
  - Coordinator ↔ R3 service: the callback and `resume_after`. The coordinator decides saves and retries; R3 decides what each step computes.
  - Coordinator ↔ `R3RunStore`: only the store knows tables, PostgREST errors, tuple keys and versions.
  - R3 ↔ R2: one read of `r2_runs.output` through `R2RunStore`; R3 never writes R2's tables.
  - Gateway ↔ app-wide limits: three optional objects; absent, the gateway is exactly today's.
- **Components:**
  - `SpecificMetricResolution` — R3 logic (unchanged), plus the resume point and the callback.
  - `McpToolGateway` + `McpProviderLimits` — per-run sessions, app-wide slots per provider.
  - `R3RunCoordinator` — tasks, callback, fence, claim, retryable split, status.
  - `R3RunStore` — `r3_runs` / `r3_run_steps` rows and codecs.
  - Routes / controllers / dependency — HTTP translation only.

### Layer 2: Justification

**B. Component Map**

| Component | Owns | Depends on | Abstracted? |
|---|---|---|---|
| SpecificMetricResolution | STEP 1 to STEP 5 (unchanged) | gateway, LLM caller | — (concrete) |
| McpToolGateway | sessions, retries, per-run + app-wide slots | MCP SDK, `McpProviderLimits` | — (concrete) |
| R3RunCoordinator | statuses, resume, fence, claim, retryable split, live dict | service factory, R3RunStore, R2RunStore | — (concrete) |
| R3RunStore | rows, tuple-key codecs, versions | Supabase AsyncClient | — (concrete) |
| controllers/routes | status codes and bodies | R3RunCoordinator | — (concrete) |

**C. Decisions & Justifications**

| Decision | Current requirement that forced it | What breaks today without it |
|---|---|---|
| One entry + `resume_after` + callback (R3-C3 approach 2) | gateway and breaker are run-scoped inside the method | splitting steps rewrites the protected method |
| Service factory per run (R3-C2, D-R3-3) | one gateway per run; one run's close can't hit another's | a finishing run closes every run's MCP sessions |
| App-wide limit per provider (R3-C2 Iteration 1) | provider limits are per key: Parallel 10, Firecrawl 2 | two runs self-induce `429`s and open breakers |
| `McpProviderLimits` bundle | three shared objects travel lifespan → factory → gateway | three loose parameters on two signatures |
| Tuple-key codec at the store + `_index` rebuild (R3-C4, D-R3-1) | exact round trip; proven failing today | a saved run can't be loaded back |
| `r3_run_steps` with `degraded` (R3-C5 Iteration 1) | per-step record, incl. breaker-open STEP 3 | no record of failures, retries and degraded work |
| `attempts` fence on every write | a late older execution must not overwrite | stale reclaim lets two executions write one row |
| Claim with stale condition (R3-C6) | a crashed run must stay retryable | a restart leaves the run unretryable forever |
| `RunSupersededError` | a lost fence inside the callback must stop the method | STEP 4 keeps spending for a superseded execution |
| Background task + live dict (R3-C7) | runs take minutes; refresh must not lose `run_id` | requests time out; page has no `run_id` |
| Live entry carries `completed_step` (Iteration 2) | progress screen needs the step without a read | every poll reads the row |
| `is_config_error` (Iteration 1) | refused keys must not offer Retry | the one retry is wasted on a bad key |
| Encoded `result` in the view (D-R3-4) | `_index` tuple keys break FastAPI's encoder | status of a finished run answers 500 |
| Four R3 settings | "as a setting" (R3-C2 Iteration 1, R3-C6) | values hard-coded |

**D. Kept Concrete / Rejected**

| Considered | Decision | Reason |
|---|---|---|
| `RunStore` Protocol for R3 | kept concrete | one implementation; the fake duck-types it |
| Public step methods driven by the coordinator (R3-C3 approach 1) | rejected | moves gateway and breaker out of the protected method |
| State-inferred skip (R3-C3 approach 3) | rejected | can't tell saved from cut short, or degraded |
| Annotated serializers in `schemas.py` (R3-C4 approach 2) | rejected | storage concerns leak into the protected schema file |
| `R3RunFailedError` | not added (R3-C7) | failures are saved on the row; nothing catches it |
| `R3RunStore.get_finished_output` | not added (D-R3-2) | no reader of R3's output exists |
| Generic run base class shared with R2 | not added | statuses, steps and execution differ (callback vs step plan) |
| Process-wide cap on active R3 runs | rejected (Iteration 1) | makes one user wait for another's whole run |
| App-wide LLM cap | not added | left out by the spec |
| Offloading the codec to a thread | not added | milliseconds at MVP sizes; sizes logged first |
| Heartbeat lease (R3-C6 approach 3) | rejected | clean shutdowns already save; revisit on B11 data |
| External job queue | rejected (R3-C7 approach 3) | no Redis/worker; stale reclaim covers process loss |
| Separate module for the live dict | not added | only the coordinator schedules and checks tasks |
| Copy of `stale_cutoff_filter` | not added (D-R3-5) | one proven filter string; a copy could drift |

### Layer 3: Wiring

**E. Dependency Direction**
```
routes → controllers → R3RunCoordinator → service factory → SpecificMetricResolution (per run) → McpToolGateway (per run) → McpProviderLimits (shared)
                                        → R3RunStore → Supabase AsyncClient
                                        → R2RunStore.get_finished_output → Supabase AsyncClient
R3 run contracts ← feature_schemas/schemas.py (no outward deps)
```

**F. Composition Root**
- **Where:** `src/app/main.py` `lifespan`, inside the existing `if settings.supabase_service_role_key:` block.
- **Selects:** `create_mcp_provider_limits(settings)`, `functools.partial(create_specific_metric_resolution, settings, llm_caller=llm_caller, provider_limits=limits)`, one shared `R2RunStore(db_client)` (also given to the R2 coordinator), `R3RunStore(db_client)`, and `R3RunCoordinator(..., stale_after_seconds=settings.r3_stale_after_seconds)`. Sets `app.state.r3_run_coordinator` and `app.state.r3_tasks = coordinator.tasks`; both None when the key is unset (`503`).
- **Teardown order:** `gather(r2.shutdown(), r3.shutdown())` → Places/Routes `aclose()` → `llm_caller.aclose()` → `db_client.postgrest.aclose()`.

**G. End-to-End Flow**
1. The request enters a route behind `get_authenticated_user` (`401` otherwise); the body is validated (`422`).
2. The controller calls the coordinator with the verified `user_id`.
3. Start reads R2's output (`404`/`503`), creates the row, schedules and returns `202`. Retry loads, pre-checks, claims (`409` on loss), claims step rows and returns `202`. Status checks memory, then the row.
4. The task builds a per-run R3, runs the method with the callback, checkpoints after a clean STEP 3, and writes `finished` or `failed` with the fence, then the step rows.
5. The page polls status until `finished` (render `result`) or `failed` (Retry or Start again).

### Layer 4: Backing (reasoning for Layer 3)

- **Why the callback, not a coordinator-driven step plan:** R3's gateway session and circuit breaker are created inside the method and shared by STEP 3 and STEP 4. A callback at the existing barrier keeps them there, so the method body and its error handling stay as they are.
- **Why a factory, not an instance on `app.state`:** `McpToolGateway.open()` returns early when already open and `aclose()` stops sessions for everyone, so runs can't share one. A zero-argument factory also lets tests swap in a fake gateway without the coordinator knowing about MCP.
- **Why the limits live in `mcp_tools.py` and are built in `lifespan`:** the gateway is the only code that knows providers and their slots. The limits must be one object per process, so the composition root builds them once and hands them down.
- **Why `get_finished_output` stays on `R2RunStore`:** it is the only module that knows `r2_runs`. R3 depends on its typed `AmenitySearchOutput`, not on R2's table.
- **Why both shutdowns run before the clients close:** a cancelled R3 task saves its failure through the database client and may still be inside an LLM call. Closing the caller or the database first would turn a clean cancel into a client error and leave the row `running`.
