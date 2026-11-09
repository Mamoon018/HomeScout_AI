# R1 Persistence Schema Design (Requirement Interpretation)

Designed with `skills/schema_definer.md` (layers 0–6). Every table, field and rule below is
derived from R1's own steps in [requirement_interpretation.py](../requirement_interpretation.py)
and from how R1 runs over HTTP ([R1_HTTP_Pause_Resume_Process_Flow.md](R1_HTTP_Pause_Resume_Process_Flow.md)).

**Inputs used (from the code, not invented):**
- **Steps:** the step list in order, from `start`, `record_clarification_answers` and `continue_after_answers`.
- **Inputs, outputs and calls:** each step's inputs, outputs and the external service it calls, from the `execute_*` methods and their return models.
- **Execution:** the HTTP request runs R1 inside the request in one or two steps (pause for answers). Retries are manual, through `/retry`, once.
- **Personal data:** customer free text and answers (see Lifecycle).

---

## 1. Schema Summary

**Tables**

| Table | Entity it holds |
|---|---|
| `r1_runs` | One R1 run: who started it, the customer's input text, its status and its retry count. |
| `r1_run_steps` | One checkpoint per non-reproducible step of a run: its status and its saved output. |

**Primary keys**
- `r1_runs`: `run_id`
- `r1_run_steps`: `(run_id, step_id)`. This serves as both row identity and business identity (see the note below).

**Foreign keys**
- `r1_runs.user_id` → `auth.users.id` (`on delete cascade`)
- `r1_run_steps.run_id` → `r1_runs.run_id` (`on delete cascade`)

**Business identity keys**
- `r1_runs`: `run_id`, generated once at start. A retry updates this same row; it never inserts a new one.
- `r1_run_steps`: `run_id + step_id`, unique (it is the primary key).

**Action identity keys:** none. R1 has no side-effecting steps (Layer 0), so no idempotency key is needed.

**Indexes**

| Index | Columns | Serves |
|---|---|---|
| `r1_runs_pkey` | `run_id` | AP1 resume lookup, AP3 status read, AP4 retry claim, AP5 R2 read |
| `r1_run_steps_pkey` | `(run_id, step_id)` | AP1 (prefix scan on `run_id`), AP4 step claim |
| `r1_runs_user_id_idx` | `user_id` | the `on delete cascade` from `auth.users` (Postgres doesn't index foreign keys on its own) |

> **Why a composite primary key and no surrogate id:** no access pattern reads a step by
> anything other than `(run_id, step_id)`, and the skill requires that pair to be unique. A
> separate `id` column would be a second identity with no reader.

---

## 2. Step Inventory (Layer 0)

Steps in run order. The step type is classified by the operation performed. Every R1 LLM call is a standard prompt-in / response-out call made through `StructuredLLMCaller.call_structured` (OpenAI → Groq), so **none is side-effecting**.

| # | Step (`step_id`) | Code | Type | Generates (validated model) | Approx. size | Persisted | Read by |
|---|---|---|---|---|---|---|---|
| — | intake | `intake_and_assemble_payload` | Deterministic (normalize, word bound, seeded `langdetect`) | `PayloadRecord` | = input | **No**; recomputed from `r1_runs.raw_input` | rebuild |
| 1 | `extraction` | `execute_and_validate` | LLM | `ExtractedRequirements` | 2–10 KB | **Yes** | rebuild (`assemble_handoff`) |
| 2 | `taxonomy_mapping` | `execute_taxonomy_mapping` (2A Op 1) | LLM | `TaxonomyMappingResult` | 1–5 KB | **Yes** | rebuild (`assemble_resolved_requirements`) |
| — | router pass 1 | `inspect_category_resolution` | Deterministic | route + `category_resolution_passes` | — | **No**; replayed | rebuild |
| 3 | `clarification_questions` | `execute_clarification_questions` (2B) | LLM | `ClarificationResult` (questions) | 1–5 KB | **Yes**, only when the router routes to 2B | rebuild, status read (questions), answer check |
| 4 | `clarification_answers` | request body → `record_clarification_answers` | **Customer input** (see note) | `list[ClarificationAnswer]` (raw answers) | < 2 KB | **Yes** | rebuild (`record_clarification_answers` makes `UserResponse`s) |
| 5 | `flag_resolution` | `execute_flag_resolution` (2A Op 2) | LLM | `FlagResolutionResult` | 1–5 KB | **Yes**, only when answers exist | rebuild (`merge_resolved_flags`) |
| — | router pass 2 | `inspect_category_resolution` | Deterministic | `category_resolution_passes` | — | **No**; replayed | rebuild |
| 6 | `category_inference` | `execute_category_inference` (M4) | LLM | `InferredCategoriesResult` | 1–5 KB | **Yes** | rebuild (`write_inferred_categories`) |
| 7 | `depth_assignment` | `execute_depth_assignment` (M5) | LLM | `DepthAssignmentResult` | < 2 KB | **Yes**, skipped when there are no categories | rebuild (`stamp_category_depths`) |
| 8 | `metric_definition` | `execute_metric_definition` (M6) | LLM | `MetricDefinitionResult` | 10–60 KB | **Yes**, skipped when no category is eligible | rebuild (`apply_metric_contract` → `write_category_metrics`) |
| — | compile plans | `compile_category_metric_plans` | Deterministic | `category_metric_plans` (R1's output) | — | **No**; recomputed | status read (result), R2 |

**Notes**
- **What is saved is the validated LLM result,** the output of each `execute_*` call, not the state it was merged into. Every merge into `RequirementInterpretationState` is already a separate deterministic method taking `(state, result)`, so the full state is recomputable from the saved results (Layer 0 rule).
- **`clarification_answers` is not one of the skill's four types.** It is the customer's own input: cheap to take in, but impossible to recompute, and it changes nothing outside the system. It is persisted with the LLM / read-only write policy (written once, after receipt). Only the raw answers are saved; the `UserResponse` entries are derived from the answers and the saved questions.
- **Skipped steps write no row.** The skip decision (no answers → no `flag_resolution`; no categories → no depth call; no eligible category → no metric call) is deterministic from earlier saved outputs, so a resume reaches the same decision.
- **Only the customer's input text lives on the run row.** `raw_input` is the input to the deterministic intake step. It can't be recomputed, so it is a run-level fact (Section 4).

---

## 3. Access Patterns (Layer 1)

| ID | Read / write | Performed by | Query |
|---|---|---|---|
| **AP1** | **Resume lookup:** load a run and all its checkpoints | coordinator, on answers (E2) and retry (E3) | `r1_runs` by `run_id` + `user_id`, embedding `r1_run_steps` by `run_id`: one PostgREST request `select=*,r1_run_steps(*)` |
| AP2 | Idempotency lookup | — | **Not needed:** no side-effecting steps |
| AP3 | Status read (refresh recovery) and paused questions | coordinator `get_run` (E4) | as AP1; the questions come from the `clarification_questions` step output, and the result is compiled from the rebuild. A run still `running` with `updated_at` older than 3 minutes is reported as `failed`, `retryable:false`, without writing (D1) |
| AP4 | Retry claim | coordinator `retry_run` (E3) | conditional `UPDATE r1_runs … WHERE status='failed' AND attempts=n`, then conditional `UPDATE r1_run_steps … WHERE step_id=<failed> AND status='failed'` |
| AP5 | R2 reads R1's finished output | R2 coordinator (R2 flow step 3) | **Deferred to the R2 work (D4).** The working assumption is as AP1 with `status='finished'`, then rebuild + `compile_category_metric_plans`. If R2 needs a stored output instead, a column is added then |

No other reads exist, and nothing is indexed for analytics.

---

## 4. Tables and Fields (Layer 2)

### `r1_runs` (run level)

| Field | Type | Column / JSON | Constraint | Justification |
|---|---|---|---|---|
| `run_id` | `uuid` | Column | PK | Identity; generated once at start. A retry updates the same row |
| `user_id` | `uuid` | Column | `NOT NULL`, FK `auth.users(id)` cascade | Every read and write filters on it (AP1, AP3–AP5) |
| `workflow_version` | `integer` | Column | `NOT NULL`, `>= 1` | Version: resume must detect R1 code changes (Layer 6) |
| `raw_input` | `text` | Column | `NOT NULL` | The customer's requirements: the input of the deterministic intake step, and the only non-recomputable run input. Written once. `NOT NULL` is database-enforced |
| `status` | `text` | Column | `NOT NULL`, `IN ('running','needs_answers','finished','failed')` | The run's state for the page; filtered in conditional updates (AP4) and in the R2 read (AP5) |
| `attempts` | `integer` | Column | `NOT NULL`, default `0`, `>= 0` | The retry limit (1); a conditional-update filter in AP4; updated on its own |
| `created_at` | `timestamptz` | Column | `NOT NULL`, default `now()` | The retention window for personal data (Layer 6) |
| `updated_at` | `timestamptz` | Column | `NOT NULL`, set by trigger | Detects a run stuck in `running` after a crash: the status read reports it as failed, not retryable, once it is older than 3 minutes (D1) |

**Not on this table (moved, so nothing is stored twice):**
- **The full `state` blob:** rebuilt from step outputs.
- **`output`:** compiled deterministically. Whether R2 needs it stored is decided during the R2 work (D4).
- **`failure_stage`, `failure_message`, `retryable`:** these describe the failed **step**, so they live on its row. A run's retryability is derived as `failed step.retryable AND attempts < 1`.

### `r1_run_steps` (step level)

| Field | Type | Column / JSON | Constraint | Justification |
|---|---|---|---|---|
| `run_id` | `uuid` | Column | `NOT NULL`, FK `r1_runs(run_id)` cascade, PK part | Identity; links a step to its run |
| `step_id` | `text` | Column | `NOT NULL`, PK part, `IN ('extraction', 'taxonomy_mapping', 'clarification_questions', 'clarification_answers', 'flag_resolution', 'category_inference', 'depth_assignment', 'metric_definition')` | Identity: the step's name. It shows where a run failed (the `failed` row) and where a retry resumes (the first step in code order with no `completed` row) |
| `status` | `text` | Column | `NOT NULL`, `IN ('started','completed','failed')` | Read policy (Layer 5); conditional updates (AP4) |
| `output` | `jsonb` | JSON | present **iff** `status='completed'` | Payload: the step's validated result, reused on resume. Shape: `{"schema_version": <int>, "data": <model dump>}` |
| `error_type` | `text` | Column | present **iff** `status='failed'` | Error: the failed step's typed error class, mapped to 502/503/500 |
| `error_message` | `text` | Column | nullable | Error: the message shown in logs and the run view; replaces today's `failure_message` |
| `retryable` | `boolean` | Column | present **iff** `status='failed'` | Error: the retry decision for this failure (AP4 pre-check) |
| `created_at` | `timestamptz` | Column | `NOT NULL`, default `now()` | When the step first ran, as basic history kept for later evaluation (Layer 6 retention) |

**No `updated_at` on steps:** a stuck run is detected at run level (`r1_runs.updated_at`, D1), and no access pattern reads a step's last-update time.

**Normalization check**
- `user_id` lives only on `r1_runs`. A step's owner is found through the foreign key, never copied.
- The JSON payload never repeats `run_id`, `step_id`, `status` or error fields.
- The payloads are not split into tables.
- The questions live only in the `clarification_questions` output, and the answers only in the `clarification_answers` output. `UserResponse`s are derived.

---

## 5. Constraints and Validations (Layer 3)

**Enforced by the database**
- Primary keys and foreign keys, both with cascade (deleting a user removes their runs; deleting a run removes its steps).
- `(run_id, step_id)` is unique, through the primary key.
- `NOT NULL` on all metadata listed above.
- Allowed values: run `status` (4 values), step `status` (`started`, `completed`, `failed`), and `step_id` (8 values).
- `output` is present iff the step is `completed`, and `error_type` and `retryable` are present iff it is `failed`.
- **A `completed` step is immutable:** a `BEFORE UPDATE` trigger rejects any update to a row whose old status is `completed`.
- RLS is on for both tables with no policies, so only the backend's service-role key reaches them (as today).

**Enforced by code**
- **One validation model per step payload,** applied before write and after read through `TypeAdapter` / `model_validate`:

  | `step_id` | Model |
  |---|---|
  | `extraction` | `ExtractedRequirements` |
  | `taxonomy_mapping` | `TaxonomyMappingResult` |
  | `clarification_questions` | `ClarificationResult` |
  | `clarification_answers` | `list[ClarificationAnswer]` |
  | `flag_resolution` | `FlagResolutionResult` |
  | `category_inference` | `InferredCategoriesResult` |
  | `depth_assignment` | `DepthAssignmentResult` |
  | `metric_definition` | `MetricDefinitionResult` |

- `output.schema_version` must equal the code's version for that step's model.
- **Business rules:**
  - answers are checked against the saved questions *before* the answers row is inserted (`record_clarification_answers` runs first);
  - `needs_answers` is only set after the `clarification_questions` step completed;
  - `finished` is only set after the rebuild compiles the plans;
  - the retry limit is 1;
  - every query filters on the verified `user_id`.

**Why the split:** uniqueness can't be guaranteed in code under concurrency (two retries of the same run), and the database can't validate the JSON contents.

---

## 6. Write Policy per Persisted Step (Layer 4)

| Step | When | Write | Concurrency guard |
|---|---|---|---|
| (run) | after the input check passes, before step 1 | `INSERT r1_runs (run_id, user_id, workflow_version, raw_input, status='running')` | new UUID, so no collision |
| `extraction`, `taxonomy_mapping`, `clarification_questions`, `flag_resolution`, `category_inference`, `depth_assignment`, `metric_definition` (LLM) | **after** the call returns a validated result | `INSERT … status='completed', output` (one statement: output and status together) | the primary key; a rejected insert means another execution owns the step, so stop |
| `clarification_answers` (customer input) | after the answers pass the check against the saved questions | `INSERT … status='completed', output=answers` | not part of this plan (duplicate answer submissions are out of scope) |
| any step, on error | when the step's call raises | `INSERT … status='failed', error_type, error_message, retryable` (or `UPDATE … WHERE status='started'` on a retry) | the primary key, or a conditional update |
| run status, on answers | when the answers request starts, before the answers row is written | `UPDATE r1_runs SET status='running' WHERE run_id AND user_id AND status='needs_answers'` (this also moves `updated_at`, so D1's 3 minutes count from the answers request, not from the pause) | conditional; 0 rows means `409` |
| run status | after each pause, finish or failure | `UPDATE r1_runs SET status=… WHERE run_id AND user_id AND status='running'` | conditional; 0 rows means stop |

**Retry (AP4), in order:**
1. `UPDATE r1_runs SET status='running', attempts=n+1 WHERE status='failed' AND attempts=n`. Zero rows means another retry won, so return `409`.
2. `UPDATE r1_run_steps SET status='started', error_type=null, error_message=null, retryable=null WHERE run_id AND step_id=<failed step> AND status='failed'`.
3. Run the step, then `UPDATE … SET status='completed', output WHERE status='started'`, or set it to `failed`.

**Allowed step transitions:** insert → `completed`, insert → `failed`, `failed → started` (retry claim), `started → completed`, `started → failed`. `completed` is final, and the trigger enforces it.

**Retryable values** (set on the failed step):
- `true` for provider unavailability or a bad body **in either phase** (the first request or the answers request), while `attempts < 1` (D5).
  - The customer's text is saved in `r1_runs.raw_input` before step 1, so a retry never asks them to type it again.
  - A retry reuses every `completed` step. A failure in `extraction` itself reruns from `raw_input`.
- `false` for the retry limit being used, a version mismatch, an unexpected error (`error_type='unexpected'`), or a run stuck in `running` (D1).
- Input that fails the input check creates no run, so it never reaches this rule.

> **Change from R1's process flow (C4):** start-phase failures used to be never retryable, because nothing reusable was saved. Checkpoints remove that reason, so they are now retryable (D5).

**Large payloads:** the threshold is **1 MB per `output`**. Above it, a payload would go to object storage with only a reference kept. The largest expected payload (`metric_definition`) is well under 100 KB, so this is **not built**.

**Number of writes per run:** 1 run insert, 5–7 step inserts, 1–2 run status updates. Today it is 2–3 whole-state writes.

---

## 7. Resume (Read) Policy (Layer 5)

**Per step row:**
- `completed`: skip the step and load its saved output.
- `started`: a crash interrupted the step during a retry. The run stays `running` and the status read reports it as `failed`, `retryable:false` after 3 minutes (D1), so the step is never rerun. The customer starts a new run.
- `failed`: rerun it only if `retryable` and the run claim succeeds (AP4). Otherwise stop and report `failed`, `retryable:false`.
- No row: run the step normally. Its own skip rule may still skip it.

**Stuck run (D1):** a run whose `status` is `running` and whose `updated_at` is older than 3 minutes is treated as crashed.
- The status read reports it as `failed`, `retryable:false`, and writes nothing.
- Retry refuses it with `409`.
- The customer starts a new run.

**Rebuild order** (on answers, retry, status and, if D4 keeps it, the R2 read):
1. Check `workflow_version`. On a mismatch, **don't resume**; the run is reported `failed`, `retryable:false`, and the customer starts a new run (Layer 6).
2. Rebuild the state from the saved outputs, in this order:
   1. `intake_and_assemble_payload(raw_input)` → `PayloadRecord`.
   2. `extraction` → `assemble_handoff(payload, extracted)`.
   3. `taxonomy_mapping` → `assemble_resolved_requirements(state, mapping)`.
   4. Router pass 1 (replayed).
   5. `clarification_questions` → `state.clarification_questions`.
   6. `clarification_answers` → `record_clarification_answers(state, answers)`.
   7. `flag_resolution` → `merge_resolved_flags(state, result)`, then router pass 2 (replayed).
   8. `category_inference` → `write_inferred_categories(state, body)`.
   9. `depth_assignment` → `stamp_category_depths(state, body)`.
   10. `metric_definition` → `apply_metric_contract` → `write_category_metrics`.
   11. `compile_category_metric_plans`.
3. The first step with no `completed` row is where execution continues. Every later step runs as usual and writes its own checkpoint.

**What this replaces:** today's rule "never save the state partway through resume, so the pass counter stays at 1". The counter is now always recomputed by replaying the router, so a partial save can't skew it.

---

## 8. Lifecycle (Layer 6)

- **Versioning:**
  - `r1_runs.workflow_version` is the R1 workflow version (it replaces today's `STATE_SCHEMA_VERSION` envelope). Each `output` carries its model's `schema_version`.
  - Either mismatch on load means the run is not resumed: it is reported `failed`, `retryable:false`, and the customer starts again (same outcome as today).
- **Retention:** runs and checkpoints are kept after completion, as basic history for later evaluation. No expiry for now; the policy will be decided in a later phase (consistent with the R2/R3 decision).
- **Sensitive data:**
  - `raw_input` and the "other" descriptions in `clarification_answers` are customer free text and may contain personal details (household, health, budget, location).
  - **Decided (D2):** they are **stored as is**. They are only reachable with the service-role key (RLS on, no policies), and deleted with the user (cascade from `auth.users`). No redaction, because the rebuild runs intake on `raw_input` and redacted text would change R1's result.
  - LLM outputs derived from them (for example `persona_facts`) are covered by the same rules.
  - A deletion period is part of the deferred retention policy, and `created_at` supports it.

---

## 9. SQL DDL

Target schema (Postgres / Supabase). It is safe to re-run, as the existing migrations are.

```sql
-- R1 runs: one row per run, tied to the user who started it.
create table if not exists public.r1_runs (
  run_id           uuid primary key,
  user_id          uuid not null references auth.users (id) on delete cascade,
  workflow_version integer not null check (workflow_version >= 1),
  raw_input        text not null,
  status           text not null
                   check (status in ('running', 'needs_answers', 'finished', 'failed')),
  attempts         integer not null default 0 check (attempts >= 0),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists r1_runs_user_id_idx on public.r1_runs (user_id);

-- R1 checkpoints: one row per non-reproducible step of a run.
create table if not exists public.r1_run_steps (
  run_id        uuid not null references public.r1_runs (run_id) on delete cascade,
  step_id       text not null check (step_id in (
                  'extraction', 'taxonomy_mapping', 'clarification_questions',
                  'clarification_answers', 'flag_resolution', 'category_inference',
                  'depth_assignment', 'metric_definition')),
  status        text not null check (status in ('started', 'completed', 'failed')),
  output        jsonb,
  error_type    text,
  error_message text,
  retryable     boolean,
  created_at    timestamptz not null default now(),
  primary key (run_id, step_id),
  constraint r1_run_steps_output_iff_completed
    check ((status = 'completed') = (output is not null)),
  constraint r1_run_steps_error_iff_failed
    check ((status = 'failed') = (error_type is not null and retryable is not null))
);

alter table public.r1_runs      enable row level security;
alter table public.r1_run_steps enable row level security;

-- updated_at moves on every run update (the status read uses it to spot a stuck run, D1).
create or replace function public.set_r1_runs_updated_at()
returns trigger language plpgsql set search_path = public as $$
begin
  new.updated_at = clock_timestamp();
  return new;
end;
$$;

drop trigger if exists r1_runs_set_updated_at on public.r1_runs;
create trigger r1_runs_set_updated_at
  before update on public.r1_runs
  for each row execute function public.set_r1_runs_updated_at();

-- A completed checkpoint is never changed.
create or replace function public.reject_completed_r1_step_update()
returns trigger language plpgsql set search_path = public as $$
begin
  if old.status = 'completed' then
    raise exception 'r1_run_steps (%, %) is completed and cannot change',
      old.run_id, old.step_id;
  end if;
  return new;
end;
$$;

drop trigger if exists r1_run_steps_completed_immutable on public.r1_run_steps;
create trigger r1_run_steps_completed_immutable
  before update on public.r1_run_steps
  for each row execute function public.reject_completed_r1_step_update();
```

### Migration from the current `r1_runs` (D3: keep it as a read-only legacy table)

The current table (from `20261105000000_create_r1_runs.sql`) is renamed and kept read-only, and the target schema above is then created next to it.

- **Why it isn't converted:** today's `state` blob holds merged state, not the per-step LLM results, so it can't fill `r1_run_steps`.
- **What the app sees:** the legacy runs are not visible to it. A status read for an old `run_id` returns `404`.

These statements run **before** the target DDL in the same migration:

```sql
-- Keep the old runs, out of the app's way.
do $$
begin
  if to_regclass('public.r1_runs_legacy') is null
     and to_regclass('public.r1_runs') is not null
     and exists (select 1 from information_schema.columns
                 where table_schema = 'public' and table_name = 'r1_runs'
                   and column_name = 'state') then
    alter table public.r1_runs rename to r1_runs_legacy;
    -- Index names are unique per schema, so free the names the new table needs.
    alter index public.r1_runs_pkey rename to r1_runs_legacy_pkey;
    alter index public.r1_runs_user_id_idx rename to r1_runs_legacy_user_id_idx;
    drop trigger if exists r1_runs_set_updated_at on public.r1_runs_legacy;
  end if;
  -- Read-only: no role may write to it (grants apply even to the service role).
  if to_regclass('public.r1_runs_legacy') is not null then
    revoke insert, update, delete, truncate on public.r1_runs_legacy
      from anon, authenticated, service_role;
  end if;
end;
$$;
```

- **Re-run safe:** the rename runs only when the old-shape table (with a `state` column) still exists and no legacy table exists yet, so running the migration again changes nothing.
- **Effect on the current R1 code:** `R1RunStore` writes the `state` and `output` columns. Once this migration runs, those columns no longer exist on `r1_runs`, so the store and coordinator must move to the new schema in the same release.

---

## 10. Assumptions and Locked Decisions

**Assumptions**
- **The LLM calls are standard calls.** All seven are prompt-in / response-out, with no provider-side objects, so none is side-effecting.
- **Deterministic steps really are deterministic.** That covers intake (seeded `langdetect`), router, merge, stamp, metric contract and compile, so rebuilding from saved results gives the same state within one `workflow_version`.
- **R1 code changes are limited to wiring.** R1's decision logic is unchanged. The coordinator gets a save hook after each `execute_*` call and a rebuild path that calls the existing deterministic methods in order. Both are wiring, not logic.

**Locked decisions**

| ID | Decision | Final answer | Source | Consequence for the build |
|---|---|---|---|---|
| D1 | What happens to a run left `running` after a crash inside the request | The status read reports it as `failed`, `retryable:false` once `updated_at` is older than 3 minutes. The customer starts again. | User | No stale-run claim for R1. Retry refuses such a run with `409`, and steps carry no `updated_at`. |
| D2 | How the customer's free text is stored until a retention policy exists | Stored as is, service-role only, deleted with the user | User | No redaction step. The rebuild can run intake on `raw_input` unchanged. |
| D3 | What the migration does with the rows already in `r1_runs` | Rename the old table to `r1_runs_legacy` and keep it read-only | User | The migration renames the table and its indexes, and revokes write grants (Section 9). Legacy runs are not visible to the app. |
| D4 | How R2 reads R1's finished output | **Deferred:** decided during the R2 work | User | AP5 stays a working assumption (rebuild + compile). `get_finished_output` is rewritten when R2 is built. If R2 needs a stored output, a column is added then. |
| D5 | Whether a failure in R1's first request can be retried | Yes, for retryable errors (provider unavailable, bad body), so the customer never retypes their input | User | `retryable` follows the error, not the phase. A retry reuses completed steps and starts from `raw_input` when `extraction` itself failed. R1's process flow rule (C4) changes accordingly. |

**Safe defaults applied**
- **Stale threshold:** 3 minutes, as a setting.
- **Retry limit:** 1 per run.
- **Large payload threshold:** 1 MB. Object storage is not built.
- **`error_message`:** nullable.

**Pending verifications**

| ID | What must be verified | Still blocks |
|---|---|---|
| V2 | A rebuild from saved step results gives the same state as the original run (live run, then compare JSON) | The rebuild path (Section 7) and D4's working assumption |
| V3 | The embedded read `select=*,r1_run_steps(*)` works through supabase-py with the service-role key | AP1 as one query (otherwise two) |

(V1, "are the existing rows dev-only", is no longer needed, because D3 keeps the rows.)

---

## Final Check (skill)

- ✅ **Every item traces to R1:** every table, field and rule traces back to R1's step inventory or to AP1–AP5, not to the skill's examples.
- ✅ **Write policies cover every persisted step:** each of the 8 persisted steps has a write policy. Every unpersisted step (intake, routers, merges, stamp, contract, compile) is deterministic and recomputed in the rebuild.
- ✅ **No fact is stored twice:**
  - `user_id` is on runs only;
  - errors are on steps only;
  - questions and answers each live in one payload;
  - no column value is repeated in JSON.
- ✅ **Every column is justified** by enforcement (`NOT NULL`, checks), lookup (`run_id`, `user_id`, `step_id`, `status`) or independent update (`attempts`, `status`, error fields).
- ✅ **Side effects:** none, so no idempotency key is needed. This is stated explicitly.
- ✅ **`run_id + step_id` is unique** (the primary key).
- ✅ **Transitions are defined,** and `completed` is immutable (trigger).
- ✅ **Nothing is added only for analytics.**
