# R1 Step Persistence (run table + step checkpoints): Implementation Plan

## Context

R1 today saves one whole-state JSON blob in `r1_runs` two or three times per run
(`R1RunStore.save_as_paused / save_answers / save_as_finished`). A failure in R1's first request is
never retryable, and a crash loses every LLM result made so far.
[R1_Persistence_Schema_Design.md](backend/src/services/deep_search/feature_context/R1_Persistence_Schema_Design.md)
replaces this with two tables:
- **`r1_runs`:** run, user, `raw_input`, status, attempts.
- **`r1_run_steps`:** one checkpoint per LLM step (and the customer's answers), holding the validated `execute_*` result.

Its locked decisions:
- **D1:** a run stuck in `running` for over **3 minutes** is reported as `failed`, not retryable. (Changed from 10 minutes at your request; the schema design doc now says 3 minutes too.)
- **D2:** free text is stored as is.
- **D3:** the old table becomes the read-only `r1_runs_legacy`.
- **D4:** R2's read is deferred.
- **D5:** first-request failures are retryable.

This plan implements that design. It changes how R1 is run, saved, resumed and retried. **It does not change R1's decision logic:** the same input and the same LLM bodies still give the same `category_metric_plans`.

**Core idea:** each of the seven `execute_*` call sites in `UserRequirementsInterpretation` goes through one checkpoint stage.
- **Saved step:** if the step has a saved result, the stage returns it with no LLM call.
- **Unsaved step:** otherwise the stage makes the call and saves the result.

A resume, a retry and the status read all replay R1's normal workflow. Saved steps return their stored results, and the deterministic merge methods run as they do today. The rebuild order and the run order are therefore the same code and can't drift apart. Every merge method after an `execute_*` call is non-raising (checked: `assemble_resolved_requirements`, `merge_resolved_flags`, `write_inferred_categories`, `stamp_category_depths`, `apply_metric_contract`, `write_category_metrics`, `compile_category_metric_plans`). All validation happens inside `execute_*`, so a saved result is always an already-validated one.

On accept, this plan is also saved as `backend/src/services/deep_search/feature_context/R1_Step_Persistence_Implementation_Plan.md` (not a build todo).

---

## Build checklist (todos, in order)

1. Migration `backend/supabase/migrations/20261106000000_create_r1_run_steps.sql`: legacy rename + revoke, new `r1_runs`, `r1_run_steps`, triggers (schema design §9).
2. Contracts in `feature_schemas/schemas.py`: `R1StepId`, `R1RunStatus` + `running`, `R1StepRecord`, reshaped `R1RunRecord`, `R1StepCheckpoints`. Add `running` to `RunResponse` / `RunErrorResponse.status` in `src/schemas/requirement_interpretation.py`.
3. Exception `CheckpointMissingError` in `src/exceptions/deep_search.py`.
4. Setting `r1_stale_after_seconds` (default 180, i.e. 3 minutes) in `src/core/config.py`, and a line in `backend/.env.example`.
5. The checkpoint stage `_checkpointed_call` plus an optional `checkpoints` keyword on 9 methods in `requirement_interpretation.py`, routing its 7 `execute_*` call sites.
6. Rewrite `r1_run_store.py` for the two tables: step-payload codec, 8 operations, keeping `dump_state` for comparison only.
7. Rewrite the flows in `r1_run_coordinator.py`: create, drive (replay + live), fail step, retry claim, status view with stuck detection.
8. Composition root `src/app/main.py` passes the stale setting. Update the retry and start notes in `src/app/api/routes/requirement_interpretation.py`.
9. Update the existing sample runner `r1_pause_resume_sample_run.py`: replace its whole-state save/load section with the step payload codec.
10. New live sample runner `feature_sample_runs/r1_step_persistence_sample_run.py`.
11. Rewrite `tests/services/deep_search/test_r1_pause_resume.py`: a two-table in-memory store, plus the checkpoint, replay, retry and stuck-run tests (§6.2).
12. Update `tests_live/test_r1_runs_live.py` and `tests_live/test_r1_runs_migration.py` for the new tables, the legacy table, the trigger and the embedded read (V2, V3).
13. Run `pytest tests`, `pytest tests_live`, and the new sample runner. Fix whatever fails.

---

## 1. File and Module Structure

| File | Change | Owns |
|---|---|---|
| `backend/supabase/migrations/20261106000000_create_r1_run_steps.sql` | new | legacy rename + revoke, the `r1_runs` / `r1_run_steps` DDL, the `updated_at` and completed-immutable triggers |
| `backend/src/services/deep_search/feature_schemas/schemas.py` | modify | `R1StepId`, `R1RunStatus`, `R1StepRecord`, `R1RunRecord`, `R1StepCheckpoints` |
| `backend/src/schemas/requirement_interpretation.py` | modify | `running` in the response status literals |
| `backend/src/exceptions/deep_search.py` | modify | `CheckpointMissingError` (replay reached an unsaved step while calls are off) |
| `backend/src/core/config.py`, `backend/.env.example` | modify | `r1_stale_after_seconds` |
| `backend/src/services/deep_search/requirement_interpretation.py` | modify | `_checkpointed_call` + optional `checkpoints` on 9 methods; no decision-logic change |
| `backend/src/services/deep_search/r1_run_store.py` | rewrite | the only module that knows Supabase: step codec + row operations on both tables |
| `backend/src/services/deep_search/r1_run_coordinator.py` | rewrite flows | run lifecycle: create, drive, checkpoints, failure, retry claim, status view |
| `backend/src/app/main.py` | modify | passes `stale_after_seconds` into `create_r1_run_coordinator` |
| `backend/src/app/api/routes/requirement_interpretation.py` | modify | Swagger notes: start failures can be retryable; retry may return `questions` |
| `backend/src/services/deep_search/feature_sample_runs/r1_pause_resume_sample_run.py` | modify | drop the removed state envelope; print the questions step payload instead |
| `backend/src/services/deep_search/feature_sample_runs/r1_step_persistence_sample_run.py` | **new (live runner)** | manual, stage-by-stage retry of a seeded run failed at `metric_definition` |
| `backend/tests/services/deep_search/test_r1_pause_resume.py` | rewrite | two-table fake store; every rule in §6.2 |
| `backend/tests_live/test_r1_runs_live.py`, `test_r1_runs_migration.py` | modify | real tables, legacy table, trigger, embedded read, migration re-run |

No new module is added beyond the migration and the sample runner. Checkpoint knowledge lives in the existing store and coordinator; R1 only gains one stage method.

---

## 2. Contracts, Blueprint and Runtime Journey

### A. Feature Map

```
Feature: Deep Search — DeepSearch (unchanged; owns the shared LLM caller)
└─ Responsibility R1: Requirement Interpretation
   ├─ UserRequirementsInterpretation — R1 workflow; decision logic unchanged
   ├─ R1RunCoordinator — run lifecycle over HTTP: create, drive, fail, retry, status
   └─ R1RunStore — Supabase adapter for r1_runs + r1_run_steps
      └─ Mechanism: Step Checkpoint Persistence (this plan)
         ├─ Stage 1: create run — R1RunCoordinator.start_run → R1RunStore.create_run
         ├─ Stage 2: checkpoint step — UserRequirementsInterpretation._checkpointed_call → R1StepCheckpoints.on_completed
         ├─ Stage 3: load run — R1RunStore.load_run (run + all step rows, one read)
         ├─ Stage 4: drive run — R1RunCoordinator._drive_run (replay saved steps, run the rest live)
         ├─ Stage 5: record failure — R1RunCoordinator._fail (failed step row, then run status)
         ├─ Stage 6: retry claim — R1RunStore.claim_retry → claim_failed_step
         ├─ Stage 7: status view — R1RunCoordinator.get_run → _view (stuck-run report, D1)
         ├─ (contract) table schema — migration, not a runtime method
         └─ (harness) fixture tests + live sample runner — not in the request path
```

### B. Data Contracts

| Contract | Purpose | Fields (`name: type`, meaning) | Mutability | Created by → Read by |
|---|---|---|---|---|
| `R1StepId` | the 8 step names | `Literal[extraction, taxonomy_mapping, clarification_questions, clarification_answers, flag_resolution, category_inference, depth_assignment, metric_definition]` | n/a | constant → all |
| `R1RunStatus` | run status | `Literal[running, needs_answers, finished, failed]` | n/a | coordinator → store, view |
| `R1StepRecord` | one decoded step row | `step_id: R1StepId` · `status: started/completed/failed` · `output: StepResult or None` · `error_type, error_message: str or None` · `retryable: bool or None` | frozen | `load_run` → coordinator |
| `R1RunRecord` | one decoded run + its steps | `run_id, user_id: str` · `status: R1RunStatus` · `raw_input: str` · `attempts: int` · `updated_at: str` · `steps: dict[R1StepId, R1StepRecord]` · derived `failed_step`, `completed` | frozen | `load_run` → coordinator |
| `R1StepCheckpoints` | what R1 sees of a run's saved steps | `completed: dict[R1StepId, StepResult]` · `allow_calls: bool` · `claimed_step: R1StepId or None` · `in_flight: R1StepId or None` · `on_completed: async (step_id, result) -> None` | **mutable**: `in_flight`, `completed`, `allow_calls` change during one request | coordinator → `_checkpointed_call` |
| `StepResult` | union of the 8 payload models | `ExtractedRequirements, TaxonomyMappingResult, ClarificationResult, list[ClarificationAnswer], FlagResolutionResult, InferredCategoriesResult, DepthAssignmentResult, MetricDefinitionResult` | frozen once saved | `execute_*` / request → store codec |
| step payload (jsonb) | stored form of a `StepResult` | `{schema_version: int, data: <model dump>}` | write-once | `dump_step_output` → `load_step_output` |
| `R1RunView` | what the page gets | unchanged fields; `status` may now be `running` | frozen | coordinator → controller |
| `CheckpointMissingError` | replay hit an unsaved step while calls are off | `step_id: R1StepId` · `stage = "replay"` | exception | `_checkpointed_call` → coordinator |

Rules:
- **An empty `completed` means a fresh run.** `allow_calls=False` is used only to rebuild a paused or finished run without any LLM call.
- **`RequirementInterpretationState` is unchanged.** It is still the one mutable handoff object inside a request, but it is never stored. It is rebuilt each request.

### C. Supporting Actors & Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
|---|---|---|---|---|
| `StructuredLLMCaller` | existing component | `call_structured(...)` | one (OpenAI → Groq chain) | `execute_*` (unchanged) |
| Supabase `AsyncClient` | existing infra client | `table(...).insert/update/select(...).execute()` | one (service-role, from `create_supabase_db_client`) | `R1RunStore` |
| `R1RunStore` | concrete adapter | the 8 operations in §D | one (the test fake duck-types it, as today) | `R1RunCoordinator` |
| `Settings` | existing config | `r1_stale_after_seconds: float` | one | composition root |

### D. Class & Method Blueprint

**`UserRequirementsInterpretation`** (`requirement_interpretation.py`). Only the additions and changed signatures are listed:

| Method | Signature | Purpose (one line) |
|---|---|---|
| `_checkpointed_call` | `(step_id: R1StepId, call: Callable[[], Awaitable[StepResult]], checkpoints: R1StepCheckpoints or None) -> StepResult [mutates: checkpoints.in_flight, checkpoints.completed] [raises: CheckpointMissingError]` | return the saved result, or call, save, return |
| `start` | `(payload, *, checkpoints=None) -> R1StartOutcome` | unchanged flow; extraction goes through the checkpoint stage |
| `generate_clarification_questions` | `(state, *, checkpoints=None) -> list[ClarificationQuestion]` | questions call goes through the checkpoint stage |
| `resolve_explicit_categories` | `(state, *, checkpoints=None) -> state` | taxonomy-mapping call checkpointed; passes `checkpoints` on to 2A Op 2 |
| `resolve_category_flags` | `(state, *, checkpoints=None) -> None` | flag-resolution call checkpointed; gate unchanged |
| `continue_after_answers` | `(state, *, checkpoints=None) -> state` | passes `checkpoints` to 2B, router, M4–M6 |
| `complete_interpretation` | `(state, *, checkpoints=None) -> state` | passes `checkpoints` to M4, M5, M6 |
| `run_persona_driven_category_inference` | `(state, *, checkpoints=None) -> state` | inference call checkpointed |
| `run_per_category_depth_calibration` | `(state, *, checkpoints=None) -> state` | depth call checkpointed; skip rule unchanged |
| `run_per_category_metric_definition` | `(state, *, checkpoints=None) -> state` | metric call checkpointed; skip rules unchanged |

`interpret`, `resume`, `parse_unstructured_input` and the terminal path pass nothing, so their behavior is identical to today's.

**`R1RunStore`** (`r1_run_store.py`):

| Method | Signature | Purpose (one line) |
|---|---|---|
| `dump_step_output` | `(step_id: R1StepId, result: StepResult) -> dict` | versioned JSON payload for one step |
| `load_step_output` | `(step_id: R1StepId, data: dict) -> StepResult [raises: StateVersionMismatchError]` | validate the payload back into its model |
| `dump_state` | `(state) -> dict` | JSON of a full state, for parity checks and printing only |
| `create_run` | `(run_id, user_id, raw_input) -> None [raises: RunStoreError]` | insert the run row as `running`, `attempts=0` |
| `insert_step` | `(run_id, step_id, result) -> bool [raises: RunStoreError]` | insert a `completed` step; False when the row already exists |
| `complete_claimed_step` | `(run_id, step_id, result) -> bool` | `started → completed` with output; False when not `started` |
| `save_step_failed` | `(run_id, step_id, *, error_type, message, retryable, claimed: bool) -> None` | insert `failed`, or `started → failed` on a retry |
| `set_status` | `(run_id, user_id, *, to: R1RunStatus, expected: R1RunStatus) -> bool` | conditional status change; False when the status moved |
| `claim_retry` | `(run_id, user_id, *, expected_attempts: int) -> bool` | `failed → running`, `attempts + 1`, one conditional update |
| `claim_failed_step` | `(run_id, step_id) -> bool` | `failed → started`, clearing the error fields |
| `load_run` | `(run_id, user_id) -> R1RunRecord or None [raises: StateVersionMismatchError, RunStoreError]` | one embedded read of the run and its steps, decoded |

Removed: `save_as_paused`, `save_answers`, `save_as_finished`, `mark_retry_started`, `save_as_failed`, `get_finished_output` (D4 deferred), `load_state`, `dump_output`, `load_output`, `STATE_SCHEMA_VERSION`, `START_PLACEHOLDER_*`. Added constants: `R1_RUNS_TABLE`, `R1_RUN_STEPS_TABLE`, `R1_WORKFLOW_VERSION = 1`, `STEP_SCHEMA_VERSION = 1`.

**`R1RunCoordinator`** (`r1_run_coordinator.py`):

| Method | Signature | Purpose (one line) |
|---|---|---|
| `__init__` | `(interpretation, store, *, stale_after_seconds: float)` | hold R1, the store and the stuck threshold |
| `start_run` | `(user_id, raw_input) -> R1RunView` | input check, create run, drive live, pause or finish |
| `submit_answers` | `(user_id, run_id, answers) -> R1RunView` | replay to the pause, check and save answers, drive on |
| `retry_run` | `(user_id, run_id) -> R1RunView` | claim run and failed step, replay, resume at that step |
| `get_run` | `(user_id, run_id) -> R1RunView` | read-only view; reports stuck runs as failed |
| `_load_for_action` | `(user_id, run_id) -> R1RunRecord [raises: RunNotFoundError, RunConflictError]` | load; a version mismatch fails the run (kept) |
| `_checkpoints` | `(run_id, record or None, *, allow_calls: bool, claimed_step) -> R1StepCheckpoints` | build the per-request checkpoint object bound to this run |
| `_drive_run` | `(raw_input: str, checkpoints) -> R1StartOutcome [mutates: checkpoints]` | start, then saved answers + continue when answered |
| `_settle` | `(run_id, user_id, outcome) -> R1RunView` | set `needs_answers` or `finished` and log it |
| `_fail` | `(run_id, user_id, checkpoints, exc, *, attempts) -> R1RunFailedError` | write the failed step, set the run `failed` (kept name) |
| `_is_stuck` | `(record) -> bool` | `running` and `updated_at` older than the threshold |
| `_view` | `(record) -> R1RunView` | now async: questions from the step row, result by replay |

`create_r1_run_coordinator(interpretation, store, *, stale_after_seconds)` keeps its role as the composition helper.

### E. Runtime Flow: Data Object Journey

A run that pauses, fails in inference after the answers, then is retried:

| # | Stage method | Reads | Produces / mutates | Rows after |
|---|---|---|---|---|
| 1 | `start_run` → `intake_and_assemble_payload` | `raw_input` | `PayloadRecord` (bad input: 422, no row) | none |
| 2 | `create_run` | run_id, user_id, raw_input | run row | `r1_runs: running, attempts 0` |
| 3 | `_drive_run` → `start(checkpoints)` | empty `completed`, `allow_calls=True` | live: extraction, taxonomy_mapping, questions; each saved by `insert_step` | 3 `completed` steps |
| 4 | `_settle` | outcome `needs_answers` | `set_status(running → needs_answers)` | run `needs_answers` |
| 5 | `submit_answers` → `load_run` | run + 3 steps | `R1RunRecord` | unchanged |
| 6 | `_drive_run(allow_calls=False)` | 3 saved results | state rebuilt to the pause; **0 LLM calls** | unchanged |
| 7 | `record_clarification_answers` | answers, rebuilt questions | `state.user_responses` (bad answers: 422, nothing written) | unchanged |
| 8 | `set_status(needs_answers → running)` + `insert_step(clarification_answers)` | answers | answers row | run `running`, 4 steps |
| 9 | `continue_after_answers(checkpoints, allow_calls=True)` | state | live flag_resolution saved; inference raises | 5 completed |
| 10 | `_fail` | `in_flight = category_inference` | failed step row (`retryable=true`, attempts 0 < 1), then run `failed` | 5 completed, 1 failed |
| 11 | `retry_run` → `claim_retry` → `claim_failed_step` | attempts 0 | run `running`, attempts 1; step `started` | as before, step `started` |
| 12 | `_drive_run(claimed_step=category_inference)` | 5 saved results + answers | replay steps 1–5 (0 calls); live inference saved by `complete_claimed_step`; live depth and metric saved by `insert_step` | 8 completed |
| 13 | `_settle` | outcome `finished` | `set_status(running → finished)` | run `finished` |
| 14 | `get_run` → `_view` | run + 8 steps | replay with `allow_calls=False` → `category_metric_plans` | unchanged |

**Shape trace:**
```
raw_input:str
 → r1_runs{run_id, user_id, workflow_version, raw_input, status=running, attempts=0}
 → per LLM step: StepResult → r1_run_steps{run_id, step_id, status=completed, output={schema_version, data}}
 → load: R1RunRecord{status, attempts, steps{step_id: R1StepRecord}}
 → R1StepCheckpoints{completed{step_id: StepResult}, allow_calls, claimed_step, in_flight}
 → replay: RequirementInterpretationState rebuilt by the existing merge methods
 → R1RunView{run_id, status, questions | result | retryable}
```

**The decision point inside `_checkpointed_call`:**
- **Saved:** the step is in `completed`, so return the saved result. No call, no write.
- **Calls off:** the step is not saved and `allow_calls` is false, so raise `CheckpointMissingError(step_id)`.
- **Otherwise:** set `in_flight`, await the call, await `on_completed` (the save), add the result to `completed`, clear `in_flight`, return the result.
- **The call raises:** `in_flight` stays set, so the coordinator knows which step failed.

### F. Method Detail

**`_checkpointed_call`**
- **Purpose:** the only place R1 touches persistence; turns every `execute_*` into "load or call-then-save".
- **What it does:** see §E's decision point. With `checkpoints=None` it just awaits the call, so today's behavior is unchanged.
- **Failure:** a `CheckpointMissingError` from replay; any error from the call or the save propagates unchanged.

**`_checkpoints` (the save callback it binds)**
- **What it does:**
  - The save for `claimed_step` uses `complete_claimed_step`; every other step uses `insert_step`.
  - A False result means another execution owns the row. The callback then raises `RunConflictError("run changed while it was running")`.
- **Failure:** a `RunStoreError` propagates.

**`_drive_run`**
- **What it does:**
  1. `start(payload, checkpoints)` with the payload from `intake_and_assemble_payload(raw_input)`.
  2. If the outcome is `finished`, return it.
  3. If it is `needs_answers` and `clarification_answers` is saved: `record_clarification_answers(state, saved answers)`, then `continue_after_answers(state, checkpoints)`, then return `finished`.
  4. If it is `needs_answers` with no saved answers, return `needs_answers`.
- **Serves:** start, answers (after the answers row is written), retry, and the status read.

**`retry_run`**
- **What it does, in order:**
  1. Load the run.
  2. Pre-check: the run must be `failed` (stuck → `409` with `retryable:false`), the failed step must be `retryable`, and `attempts < 1`. Otherwise `409`.
  3. `claim_retry`; False means `409` "Another retry of this run already started".
  4. `claim_failed_step`; False means the run is saved `failed`, not retryable, then `409`.
  5. `_drive_run` with `claimed_step`.
  6. `_settle`.
- **May return `needs_answers`** when the failed step was `clarification_questions`.

**`get_run` / `_view`**
- **What it does:**
  - **Version mismatch:** `failed`, `retryable:false`, no write.
  - **Stuck:** `failed`, `retryable:false`, a WARN line, no write.
  - **`running`:** status only.
  - **`needs_answers`:** questions from the `clarification_questions` output.
  - **`finished`:** `_drive_run(allow_calls=False)` → `category_metric_plans`.
  - **`failed`:** `retryable` = failed step's `retryable` and `attempts < 1`; false when no step failed.
  - A `CheckpointMissingError` during replay reads as `failed`, not retryable.

**`insert_step` / `load_run`**
- **What they do:**
  - `insert_step` maps PostgREST `APIError` code `23505` (unique violation) to False. Every other `APIError` / `httpx` error becomes `RunStoreError`, as today.
  - `load_run` uses `select("*, r1_run_steps(*)")` filtered on `run_id` and `user_id`.
  - It checks `workflow_version` first, then decodes each completed output with `load_step_output`. Either mismatch raises `StateVersionMismatchError`.

**Migration**
- **What it does:**
  - The legacy block from schema design §9 runs first: rename to `r1_runs_legacy` only when the old-shape table exists, rename its two indexes, drop its trigger, revoke writes. Then the target DDL runs.
  - Every statement is idempotent.

**Retryable split (written by `_fail`)**

| Error | `error_type` | `retryable` |
|---|---|---|
| any `R1_STAGE_ERRORS` member (provider unavailable or bad body), either phase | its class name | `attempts < 1` (D5) |
| any other exception inside a step | `unexpected` | false |
| failure with no `in_flight` step (replay, store, coordinator) | no step row; run `failed` | false (derived) |

---

## 3. Async Structure

| Layer / group | Operations and I/O | Data dependency | Placement | Ordering |
|---|---|---|---|---|
| HTTP route → coordinator | one coroutine per request | n/a | event loop | awaited |
| Load + checks | `load_run` (one HTTP call to PostgREST) | everything after needs the record | event loop (async client) | sequential |
| Retry claim | `claim_retry` → `claim_failed_step` | the step claim is valid only after the run claim wins | event loop | sequential |
| Replay | intake, `langdetect`, the merge methods, router | each merge reads the previous one's state | event loop, inline (trivial CPU, ms) | sequential |
| Live step + save | `execute_*` (LLM HTTP) → `insert_step` / `complete_claimed_step` | step N+1 reads state from step N; the save must land before the next call starts | event loop | sequential |
| Failure write | `save_step_failed` → `set_status` | the run status must follow the step row | event loop | sequential |

**Blocking check:**
- **No blocking calls.** All database calls go through the existing async `supabase` client (`acreate_client`), and LLM calls through the existing async caller.
- **No worker is needed.** Replay is small, CPU-only work with no I/O, so it runs inline.

**No concurrency is introduced.** A save could overlap the next LLM call, because they don't depend on each other's data. It stays sequential anyway: `in_flight` must name exactly one step for failure accounting, and the save must be durable before work that depends on it starts.

---

## 4. Drift Entries (per method)

**`_checkpointed_call`**
- **Core behavior:** load a saved step result, or call and save it.
- **Drifts handled:**
  - **Replay reaches an unsaved step while calls are off.** The rows are inconsistent, for example a `needs_answers` run without a questions row. Caught in the **core**; **rejected** with `CheckpointMissingError` instead of making an unplanned paid call.
  - **The save fails after the LLM call succeeded.** Caught at **infra** (store). **Propagated**; `in_flight` stays set, so the step is recorded as failed when the store is reachable. Otherwise the run stays `running` and D1 reports it.
- **Left out (why):**
  - Re-validating a loaded result against state: it was validated when saved, under the same deterministic state. *Trust.*
  - Retrying the save: unsafe without knowing whether the first write landed. *Trust.*

**`R1RunStore.insert_step` / `complete_claimed_step`**
- **Core behavior:** write one completed checkpoint.
- **Drifts handled:**
  - **The row already exists** (another execution, double submit). Caught at **infra** (the primary key, `23505`); **reject** by returning False, and the coordinator raises `409`.
  - **An update would hit a completed row.** Caught at **infra** (the immutability trigger); **propagated** as `RunStoreError`, loud.
- **Left out (why):**
  - `user_id` filter on step writes: `run_id` comes from a run already loaded with the verified `user_id` in this request, and the steps table has no `user_id` column. *Not live.*
  - Payload size check (1 MB): the largest payload is under 100 KB. *Imaginary.*

**`R1RunStore.load_run`**
- **Core behavior:** read the run and its steps in one call, decoded.
- **Drifts handled:**
  - **`workflow_version` or `schema_version` differs from the code.** Caught in the **core** of the codec; **rejected** with `StateVersionMismatchError`.
  - **The embedded read is unsupported** (V3 unconfirmed). **De-masked:** an empty or missing `r1_run_steps` key raises `RunStoreError`, never "no steps".
- **Left out (why):**
  - Partial rows from concurrent writes: a single SELECT sees one snapshot. *Not live.*

**`R1RunCoordinator.start_run`**
- **Core behavior:** check the input, create the run, drive live, pause or finish.
- **Drifts handled:**
  - **Bad input.** Caught at the **edge** (the intake check before the insert); **rejected** with `422`, no row.
  - **An LLM step fails.** Caught in the **core** (`_fail`); **rejected** with `502`/`503`; the step row is retryable (D5).
  - **The status update finds the run not `running`.** Caught in the **core**; **reject**, `409`.
- **Left out (why):**
  - Duplicate start requests: out of scope (schema design). *Trust.*

**`R1RunCoordinator.submit_answers`**
- **Core behavior:** rebuild to the pause, check and save the answers, drive on.
- **Drifts handled:**
  - **The run is not `needs_answers`.** **Core**; **reject**, `409`.
  - **Answers don't match the questions.** **Core**; **reject**, `422`, before any write.
  - **The status moved between load and update.** **Core** (conditional `set_status`); **reject**, `409`.
- **Left out (why):**
  - A double answers submission racing past the status update: out of scope (schema design). The primary key still rejects the second insert. *Trust.*

**`R1RunCoordinator.retry_run`**
- **Core behavior:** claim, replay, resume at the failed step.
- **Drifts handled:**
  - **Two retries at once.** **Infra** (the conditional `claim_retry`); **reject**, `409` for the loser.
  - **A stuck `running` run.** **Core** (`_is_stuck`); **reject**, `409` with `retryable:false` (D1).
  - **The step claim fails after the run claim won.** **Core**; **reject**: the run is saved `failed`, not retryable, then `409`.
  - **The failed step is not retryable, or the limit is used.** **Core**; **reject**, `409`.
- **Left out (why):**
  - A stale-run reclaim: decided out by D1. *Not live.*

**`R1RunCoordinator.get_run` / `_view`**
- **Core behavior:** a read-only view of the saved run.
- **Drifts handled:**
  - **A crashed run left `running`.** **Core** (`_is_stuck`); **recover-degrade**: reported `failed`, not retryable, with a WARN line.
  - **The saved data can't be read** (version mismatch, missing checkpoint). **Core**; **degrade**: `failed`, not retryable, no write.
- **Left out (why):**
  - Caching the compiled plans: the replay is CPU-only and costs milliseconds. *Not live.*

**`_is_stuck`**
- **Core behavior:** compare `updated_at` with now minus the threshold.
- **Drifts handled:**
  - **The timestamp format differs from what's parsed.** **Core**; **reject**: `datetime.fromisoformat` raising is loud (`RunStoreError`), never a silent "not stuck".
- **Left out (why):**
  - Clock skew between the database and the backend: the 3-minute threshold is far larger than the skew (seconds at most). *Trust.*
  - A slow but live run passing 3 minutes: a full R1 request makes at most 7 LLM calls of seconds each, so it finishes well inside 3 minutes. If one ever runs longer, the status read reports it failed while it is still working, and its final status write still lands, because `set_status` filters on `running`. *Trust; revisit if live runs approach 3 minutes.*

---

## 5. Log Plan

All lines are JSON on `DEEP_SEARCH_LOGGER_NAME` and carry `run_id` (via `run_id_var`) and `user_id`.

| Event | Level | Node type | Driving state |
|---|---|---|---|
| `r1_run.created` | INFO | state change | `workflow_version`, `word_count` |
| `r1_run.loaded` | INFO | boundary (database in) | `status`, `attempts`, `completed_steps`, `failed_step` |
| `r1_step.saved` | INFO | state change | `step_id`, `path` (insert / claimed), `schema_version`, `output_chars` |
| `r1_run.paused` / `r1_run.finished` / `r1_run.answers_saved` | INFO | state change | as today (question count, plan count, answer count) |
| `r1_run.retry_started` | INFO | state change | `attempts`, `claimed_step` |
| `r1_run.failed` | ERROR | endpoint | `step_id`, `error_class`, `retryable`, `attempts`, `message` |
| `r1_run.stuck_reported` | WARN | silent drift | `status`, `updated_at`, `stale_after_seconds` |
| `r1_run.status_degraded` | WARN | silent drift | found / expected version, or `missing_step` |
| `r1_run.rejected` | INFO | boundary (reject handled) | `reason` (wrong_status, not_retryable, cas_lost, step_conflict, answers_invalid, not_found) |
| `r1_run.store_error` | ERROR | boundary (database out) | `operation`, `error_class`, `detail` (as today) |

No line per replayed step: replay is deterministic from rows already reported by `r1_run.loaded`.

---

## 6. Sample Runner and Fixture Set

### 6.1 Live sample runner: `feature_sample_runs/r1_step_persistence_sample_run.py` (new)

**How to run it:** from `backend/`:

```bash
python -m src.services.deep_search.feature_sample_runs.r1_step_persistence_sample_run
```

**What it seeds:** one run, as the previous steps would leave it, through the real step codec:
- `raw_input`: at least 100 English words, so replay's intake passes.
- Completed rows: `extraction`, `taxonomy_mapping`, `clarification_questions`, `clarification_answers`, `flag_resolution`, `category_inference`, `depth_assignment`.
- A **failed, retryable `metric_definition`** row.
- The run is `failed` with `attempts=0`.

**The seeded case is new.** It is a night-shift nurse with a toddler and an elderly cat, using valid taxonomy nodes. It is not the retired-couple case from `r1_pause_resume_sample_run.py`, and not any worked pair in `metric_definition_instruction.py` or the other R1 prompts (to be checked against them when writing).

**How it stores rows:** in a small in-memory row holder defined in the runner, with the store's method names and the real `dump_step_output` / `load_step_output`. Nothing is written to Supabase or to disk. Earlier mechanisms are not re-run.

**It drives the real `R1RunCoordinator.retry_run` and then `get_run`.** One live LLM call (`metric_definition`).

**What it prints, one titled section each:**
1. Seeded run and step rows.
2. Retry claim: attempts 0 → 1, step `failed → started`.
3. Replay: provider attempts during replay (must be 0), rebuilt categories and depths.
4. `metric_definition` provider attempts and raw body (read from `LLM_PROVIDER_ATTEMPT_EVENT` / `LLM_PROVIDER_RAW_BODY_EVENT`, as `r1_pause_resume_sample_run.py` does).
5. The saved checkpoint row (status, `schema_version`, size).
6. Run status.
7. Status read: the replayed `category_metric_plans`, 0 calls, equal to the retry result.

**On a typed failure:** the class, `stage` and message, with exit code 1.

### 6.2 Fixture set (pytest, no live calls): `tests/services/deep_search/test_r1_pause_resume.py`

**`FakeRunStore` is rewritten** as two in-memory tables. It enforces:
- the `(run_id, step_id)` uniqueness;
- the completed-immutable rule;
- the conditional updates;
- the JSON round trip through the real codec.

`FakeStructuredProvider` stays.

**Kept and adapted:** pause and no-pause parity with `interpret()`, answer recording, invalid answers, questions generated once, input check creates no row, ownership, restart with fresh objects.

**New:**

| Test | Passes when |
|---|---|
| one row per LLM step | a paused run has 3 completed rows; a finished run has 7–8, each with the right `step_id` |
| replay makes no calls | the answers and status paths call the provider 0 times for saved steps |
| replay equals live (V2) | the rebuilt state's `dump_state` equals the live state's |
| start failure retryable (D5) | a failure in `category_inference` during start gives `retryable:true`; retry calls only inference, depth, metric |
| extraction failure retry | retry reruns extraction from `raw_input` with no retyping |
| claimed step path | the retried step row goes `failed → started → completed`, not a new row |
| retry limit | a second failure after one retry gives `retryable:false` |
| concurrent retries | the second `claim_retry` returns False, giving `409` |
| stuck run (D1) | `running` older than the threshold reads as failed and not retryable, and retry gives `409`; younger reads `running` |
| missing checkpoint | a `needs_answers` run without a questions row reads as failed, not retryable |
| version mismatch | `workflow_version` 2 or step `schema_version` 2 reads as failed, not retryable |
| completed immutable | the fake rejects an update of a completed row; no code path tries one |
| no checkpoints, same behavior | `interpret()` and the mechanism tests pass unchanged |

**Live (`tests_live`):**
- `test_r1_runs_live.py` repeats parity, failure, retry and ownership on the real tables, and asserts the embedded read (V3).
- `test_r1_runs_migration.py` applies both migration files twice. It asserts the new columns, the existing `r1_runs_legacy` table refusing service-role writes, the trigger rejecting an update of a completed step, and that no app code creates or alters `r1_runs` or `r1_run_steps`.

---

## 7. Verification

1. `cd backend && .venv/Scripts/python.exe -m pytest tests -q`: the whole existing suite plus §6.2 passes.
2. **Apply the migration to the dev project** (Supabase CLI from `backend/`, or the live migration test), then run `pytest tests_live -q` with the live settings set. A missing setting skips with its name.
3. **Run the sample runner.** The replay section shows 0 provider attempts, and the status-read plans equal the retry result.
4. **Manual HTTP check (Swagger):**
   - Start a run with flags → `needs_answers`.
   - Answer → `finished`.
   - `GET` → same result.
   - Force a provider failure (bad key in `.env`) on start → `502`/`503` with `retryable:true`.
   - Fix the key, then retry → `finished`, with only the failed and later steps called (log `r1_step.saved` lines).

---

## 8. Architecture & Modularity Decisions

### Layer 1: Glance

- **Shape:** R1's workflow reaches persistence through one stage method and a per-request checkpoint object. The coordinator builds that object over a concrete Supabase store.
- **Seams:**
  - The checkpoint object: the coordinator decides what is saved; R1 decides when a step happens.
  - The store: the only code that knows table names, PostgREST errors and payload versions.
- **Components:**
  - `UserRequirementsInterpretation` — R1 workflow; one new stage method, no logic change.
  - `R1StepCheckpoints` — saved results, call permission and save callback for one request.
  - `R1RunCoordinator` — run lifecycle: create, drive, fail, retry, status.
  - `R1RunStore` — rows of `r1_runs` and `r1_run_steps`, plus the payload codec.

### Layer 2: Justification

**B. Component Map**

| Component | Owns | Depends on | Abstracted? |
|---|---|---|---|
| UserRequirementsInterpretation | step order, gates, merges (unchanged) | StructuredLLMCaller, R1StepCheckpoints | — (concrete) |
| R1StepCheckpoints | saved results + save callback for one request | — | — (dataclass) |
| R1RunCoordinator | statuses, retry rules, stuck rule | UserRequirementsInterpretation, R1RunStore | — (concrete) |
| R1RunStore | SQL-facing rows, codec, versions | Supabase AsyncClient | — (concrete) |

**C. Decisions & Justifications**

| Decision | Current requirement that forced it | What breaks today without it |
|---|---|---|
| `_checkpointed_call` wraps the 7 `execute_*` sites | save each LLM step, skip saved ones (schema design §6, §7) | no save point after each step; a retry repeats paid calls |
| Optional `checkpoints` keyword, default None | `interpret()`, tests and sample runs must keep today's behavior | every existing caller and test would need edits |
| Replay through R1's own workflow, not a rebuild list | rebuild order must equal run order (schema design §7) | a second sequence can drift from R1's gates and skip rules |
| `allow_calls` flag | answers and status paths must make no LLM call | a missing row would trigger an unplanned paid call silently |
| `claimed_step` on the checkpoint object | a retried step updates its row (schema design §6) | the retry inserts a duplicate and hits the primary key |
| Conditional updates for status and claims | one retry wins (AP4); statuses must not regress | double retries both run and double-spend |
| `stale_after_seconds` injected from Settings | D1 threshold "as a setting" | the threshold is hard-coded in the coordinator |

**D. Kept Concrete / Rejected**

| Considered | Decision | Reason |
|---|---|---|
| `RunStore` Protocol | kept concrete | one implementation; the test fake duck-types it, as today |
| Checkpointer interface for R1 | rejected | one implementation; a dataclass with a callback is enough |
| Context variable carrying the checkpoints | rejected | hidden input to 9 methods; the explicit keyword is visible in signatures |
| Coordinator calling `execute_*` and merges itself | rejected | duplicates R1's gates and skip rules outside R1 |
| Separate `rebuild_state` sequence | rejected | a second copy of the step order |
| Storing the whole state again | rejected | the schema design removes the blob (no fact stored twice) |
| New modules for checkpoints or replay | not added | the store and coordinator already own these concerns |
| Overlapping a save with the next LLM call | not added | failure accounting needs one `in_flight` step |
| `get_finished_output` | removed | D4 deferred; R2 is not built |

### Layer 3: Wiring

**E. Dependency Direction**
```
routes → controllers → R1RunCoordinator → UserRequirementsInterpretation → StructuredLLMCaller
                                       → R1RunStore → Supabase AsyncClient
R1RunCoordinator builds R1StepCheckpoints (save callback → R1RunStore) → passed into UserRequirementsInterpretation
```

**F. Composition Root**
- **Where:** `src/app/main.py` `lifespan`.
- **Selects:** the service-role async client (`create_supabase_db_client`) and `R1RunStore(db_client)`, plus `create_r1_run_coordinator(interpretation, store, stale_after_seconds=settings.r1_stale_after_seconds)`, built only when `SUPABASE_SERVICE_ROLE_KEY` is set (as today).

**G. End-to-End Flow**
1. The request enters a route behind `get_authenticated_user`.
2. The controller calls the coordinator with the verified `user_id`.
3. The coordinator loads (or creates) the run through `R1RunStore`.
4. It builds `R1StepCheckpoints` from the saved steps.
5. It calls R1's entry points with them; saved steps return stored results, and new steps are called and saved through the callback.
6. It sets the run status (`needs_answers`, `finished` or `failed`) with a conditional update.
7. The controller maps the `R1RunView` or the typed error to the HTTP response (unchanged).

### Layer 4: Backing (reasoning for Layer 3)

- **Why the checkpoint object goes into R1 instead of R1 calling the store:** R1 stays free of Supabase. Its only new dependency is a plain dataclass, so the mechanism tests run with `checkpoints=None` or an in-memory callback.
- **Why the coordinator, not R1, builds it:** retry rules, `claimed_step` and the attempts fence are run-lifecycle decisions the coordinator already owns.
- **Why replay instead of a stored state:** the state is fully recomputable from the saved results through methods that already exist and never raise. One code path serves start, answers, retry and status, so the order can't diverge.
- **Why the composition root passes only a number:** the threshold is the only new configurable value. The store and client wiring are unchanged from today.
