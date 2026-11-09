# R1 Feature Process Flow: Pause and Resume over HTTP

R1 (Requirement Interpretation) is used by a customer from a web page. A run finishes in one request, or it pauses once for clarification and finishes in a second request.

R1 needs **6 components**. Four of them add the pause, the saving and the endpoints. The other two connect them and prove nothing changed. R1's decision logic is reused exactly as it is.

## Finalized Problem Statement

> The system must turn a customer's free-text requirements into R1's structured specification in **one or two steps**, depending on whether R1 finds unclear categories. When it does, the system must **save all work done up to that point** under the run's ID and **return the clarification questions to the customer** before going any further. It must ask them **at most once** per run. When the customer answers, the system must **save the answers to the same run** and **continue R1 from the saved state, not from the beginning**. It must not recompute anything already decided. Both steps must use **one state for the run**, saved outside the process so it survives restarts and separate requests over HTTPS. Throughout, the run must report **one clear status**: needs answers, finished or failed. Only a **finished** output, saved under the **run ID created when the run started**, may be handed to R2. All of this must happen **without changing R1's current results** for runs that need no clarification, and without breaking the existing tests and sample runs.

## Scope Boundary

- **Do not change:** R1's decision logic. This covers how it extracts and resolves categories, decides what is still unclear, generates questions, uses the answers, and produces each field's value. Given the same input and the same answers, R1 must produce the same output it does today.
- **May change or add:** everything around that logic that the problem statement requires: entry points and HTTP endpoints, splitting the run at the clarification pause, replacing the terminal `input()` with answers supplied in a request, and saving and loading the run's state under its run ID.
- **Rule for every addition:** each component must trace back to a requirement in the Finalized Problem Statement.

## What Already Exists and Is Reused As-Is

| Built-in | Where | Used for |
|---|---|---|
| R1 decision logic: extraction, category resolution (2A), router, question generation, flag resolution (2B), inference, depth, metrics | `UserRequirementsInterpretation` | Every step that produces a value |
| Pass cap (`category_resolution_passes >= 2` → no more questions) | `inspect_category_resolution` | "At most once", already guaranteed |
| Shared LLM caller and the R1 factory | `create_structured_llm_caller`, `create_requirement_interpretation` | Building R1 inside the app |
| Typed R1 errors, each with a `stage` | `src/exceptions/deep_search.py` | Marking a run "Failed" with the reason |
| FastAPI app, lifespan, error handler | `src/app/main.py` | Hosting the endpoints |
| Supabase project, client and migrations folder | `src/clients/supabase.py`, `backend/supabase/migrations/` | The database |

**Two gaps the code shows:**

- **The generated questions are not stored on the state.** `collect_clarification_responses(state, result)` receives them as an in-memory argument. A second request can't see them unless they are saved.
- **The terminal prompts are part of the tested behaviour.** `test_mechanism_2_clarification.py` replaces `input()` with scripted answers, and `category_resolution_sample_run.py` calls `collect_clarification_responses` directly. Both have to keep working.

## Component Order

```
C1 Resumable R1 entry points ──► C4 R1 run coordinator ──► C5 HTTP endpoints
C2 State serialization ──► C3 Run store ──┘                          │
                                              C6 Verification of C1–C5
```

## Mapping to the R1 Process Flow

| Process flow steps | Component |
|---|---|
| 3–4, 5, 7, 13–15 | C1 |
| 8, 12, 13, 17 (saving and loading the state) | C2 + C3 |
| 2, 9, 18, failure handling | C3 + C4 |
| 1, 10, 11, 19 | C5 |
| 20 (R2 reads by run ID) | C3 (reads finished runs only) |

---

## C1. Resumable R1 Entry Points

### Goal of Component

R1 can stop once its questions are ready and later continue from that point, given the answers as data instead of terminal input. The current one-call `interpret()` keeps working.

### Problem It Aims to Solve

Today the pause is an `input()` call in the middle of `run_explicit_category_resolution`, so R1 only works in a terminal. The questions exist only in memory, so a later request can't match answers to them.

**Traces to:** "return the clarification questions … before going any further", "continue R1 from the saved state", "must not recompute anything already decided", "one or two steps".

### Mandatory Sub-Tasks Independent of Approaches Taken

- Store the generated questions on `RequirementInterpretationState` as a new optional field, empty by default so existing code is unaffected.
- **Start part:** takes the payload that already passed the input check (`intake_and_assemble_payload`, run by the coordinator in C4), then extraction → 2A pass 1 → router. If there are no category flags, continue straight to the end. If there are flags, generate the questions, store them, and stop.
- **Answer recording:** one new R1 method takes the raw answers and builds the `UserResponse` entries on the state (see Finalized Decisions).
- **Resume part:** call the answer-recording method → `continue_after_answers(state)`.
- **Steps after answer recording:** `continue_after_answers(state)` runs `resolve_category_flags` → router → inference → depth → metrics on its own, so a retry (C4) can run them on the saved state without recording answers again.
- The step that finishes R1 (inference → depth → metrics) is shared by the start part, the resume part and `interpret()`, so that logic exists only once.
- `interpret()`, `clarify_unmapped_categories` and the terminal prompts keep their current behaviour, so the scripted-`input()` tests and the sample runs still pass.
- The resume part never calls question generation.

### Finalized Approach

**Two explicit methods.**

- `start(payload)` takes the checked `PayloadRecord`, so the input check runs only once, then runs the start part and returns the run's **status plus state**. The status is `needs_answers` when R1 paused with questions, or `finished` when no category flags were found and R1 ran to the end.
- `resume(state, answers)` records the answers, then calls `continue_after_answers(state)`, and returns a finished state.
- `continue_after_answers(state)` runs the steps after answer recording. Retry (C4) calls it directly with the saved state, whose answers are already recorded.
- `interpret()` becomes input check → start → answers from the terminal → resume, so the one-call path and the web path run the same code.

### Finalized Decisions

- **What `start` returns:** a status plus the state, not two distinct result types.
- **Where answers become `UserResponse` entries:** a new R1 method takes the raw answers and builds the `UserResponse` entries on the state. Both paths call the same method:
  - **Web path:** `resume` calls it with the answers from the request.
  - **Terminal path:** `collect_clarification_responses` reads the answers through the existing prompts, then calls the same method.

  Because both paths share the method, the stored `UserResponse` entries can't differ between them.
- **Answer format:** unchanged from the terminal, since the web page can send the same format.
  - Each answer is the chosen option number (1–5).
  - When the customer picks "other", the answer also carries their description.
  - The stored `UserResponse` keeps today's rule: the chosen option's text, or the customer's description for "other".
- **Second router call on resume:** kept.
  - **Decision:** on resume, the router runs a second time, so the pass counter ends at 2 exactly as in today's one-call run. Neither the counter nor the router's decision logic changes.
  - **Reason:** it costs nothing, keeps the resumed state identical to a one-call run (C6 parity), and leaves R1's logic untouched. The web flow relies on the run's status, not the counter.
- **How much `interpret()` may be restructured:** as much as the new approach requires, since making start, resume and retry work is the goal of this implementation. The limit is the problem statement's: R1's decision logic and results stay the same, and the existing tests and sample runs keep passing.

---

## C2. State Serialization

### Goal of Component

A paused or finished `RequirementInterpretationState` can be turned into JSON and back with nothing lost.

### Problem It Aims to Solve

The state mixes dataclasses (one frozen) with Pydantic models, and uses `dict[int, UserResponse]` (JSON turns the int keys into strings). Saving it in a database requires converting it to JSON and back without loss.

**Traces to:** "save all work done up to that point", "saved outside the process so it survives restarts and separate requests".

### Mandatory Sub-Tasks Independent of Approaches Taken

- Round-trip tests for a paused state and a finished state: the loaded state equals the original.
- Int keys, the frozen `PayloadRecord`, `Literal` and enum fields, and `None` fields all come back with the correct types.
- Every saved state carries a version number.

### Finalized Approach

**Pydantic `TypeAdapter` over the existing classes.**

- Pydantic reads and writes the stdlib dataclasses and models of `RequirementInterpretationState` as they are, with no schema changes.
- The state is saved as JSON, so it stays readable in the database.

### Finalized Decisions

- **Version mismatch after a deploy:** reject the run.
  - **Decision:** if the saved state's version doesn't match the code's current version, the run is marked "Failed" and the customer is asked to start again.
  - **Reason:** paused runs are short-lived and rarely caught by a deploy, so writing code to upgrade old states isn't worth it.
  - The version is checked when the state is loaded. A mismatch raises a typed error that the coordinator (C4) records as "Failed".
- **Re-checking on load:** accepted. Loading through Pydantic re-runs the schema validators, for example the "exactly one 'other' option" rule. Saved values already passed them once, so this is fine.

---

## C3. Run Store (database)

### Goal of Component

Each run is one database row identified by its run ID and tied to the logged-in user who started it. The row holds the status, the single R1 state, the finished output and the failure reason. Other code can create, load and update it, and R2 can read only finished outputs.

### Problem It Aims to Solve

No table or write path exists for deep search. The backend's Supabase client currently handles authentication only, using the publishable key with no user session. It is also synchronous, so database calls made through it inside async routes would block every other request, including long R1 LLM calls.

**Traces to:** "one state for the run, saved outside the process", "one clear status: needs answers, finished or failed", "finished output, saved under the run ID created when the run started", "only a finished output may be handed to R2".

### Mandatory Sub-Tasks Independent of Approaches Taken

- A migration in `backend/supabase/migrations/` for an `r1_runs` table with these columns:
  - `run_id`
  - `user_id`: the verified user who started the run
  - `status`: one of `needs_answers`, `finished`, `failed`
  - `state` (JSON): the single R1 state, including the generated questions and the customer's answers
  - `output` (JSON): R1's finished output for R2
  - `failure_stage`, `failure_message`
  - `retryable` (true/false): set when the run is saved as failed (C4 decides the value)
  - `attempts`: the number of retries made, used to enforce the retry limit of 1
  - `created_at`, `updated_at`
- Row-level security switched on for `r1_runs` with no public policies, so the publishable key used by the frontend can't read or write the table; only the backend's service-role key can.
- A new setting for the Supabase service-role key.
- A separate async Supabase client for database work, built with `acreate_client` and the service-role key. The existing sync client stays for auth.
- Every save is a single-row update, so the status and the data always change together.
- Every read and write filters on the verified `user_id` as well as the `run_id`.
- **Never save the state partway through resume.** Only the finished state is written after "Save the answers". The saved copy stays clean, with the pass counter at 1, so a retry (C4) runs the second router call exactly as the first attempt did.
### Finalized Approach

**`supabase-py` async client (table API) with the service-role key.**

- The backend creates a separate `AsyncClient` (`acreate_client`) for database work, so every call is awaited and never blocks the event loop: `await client.table("r1_runs").update({...}).eq("run_id", run_id).execute()`.
- The existing sync client in `src/clients/supabase.py` stays as it is, for auth only.
- All store operations below use this async client.

### Finalized Decisions

- **Blocking calls:** replaced with the async client, not run in a thread pool.
- **When the row is created:** after the input passes R1's input checks (`intake_and_assemble_payload`).
  - **Reason:** incomplete input has no value, so there's no need to store it. Invalid input is rejected without a run ID.
- **Backend access:** the service-role key with a backend filter on `user_id`, in two layers:
  - **Layer 1, only logged-in users reach R1 (already built).** The R1 router sits behind `get_authenticated_user`, the same way `/api/user_welcome` does: `APIRouter(dependencies=[Depends(get_authenticated_user)])`. It verifies the access-token cookie and returns the user's `user_id`, or rejects the request with 401.
  - **Layer 2, every stored run is tied to its user.** When the backend creates a run, it takes `user_id` from the verified token only, never from the request body, so a customer can't claim to be someone else. Every read and write adds `user_id = <verified user_id>`.
  - **Who enforces it:** backend code, through the filter on every query.
  - **Trade-off:** small setup (one client, one extra filter), with no issue over long pauses. A missing filter in the backend could expose another user's run, so every store operation must include it.
- **Answers:** no separate column. They live in `state.user_responses`.
- **Output:** a separate `output` column, so R2 reads a stable, smaller contract than the full state.

### Store Operations

| Operation | What it does |
|---|---|
| **Create a run** | Adds a new row for the run under its run ID and the verified `user_id`, after the input checks pass and before the rest of R1 runs. |
| **Save as paused** | Writes the R1 state, with the generated questions on it, to the run's row and sets the status to `needs_answers`. |
| **Save the answers** | Writes the customer's answers (in `state.user_responses`) to the same run's row before R1 resumes, so they are kept even if the resume fails. |
| **Save as finished** | Writes the final state and R1's output to the run's row and sets the status to `finished`. |
| **Mark retry started** | Increases the run's `attempts` by one before a retry runs. |
| **Save as failed** | Sets the run's status to `failed`, records the stage that failed and the error message, and sets `retryable`. It leaves the saved state untouched, so a retry can reuse it. |
| **Load a run** | Reads the run's row by run ID and `user_id` and returns its status, its `retryable` flag and `attempts`, and its state, converted back from JSON (C2). |
| **Get the finished output** | Returns R1's output for R2 by run ID and `user_id`, or nothing if the run's status isn't `finished`. |

### Flow with Authentication

1. A registered user logs in and gets the access-token cookie (existing).
2. They submit requirements. `get_authenticated_user` verifies them, and the run is created with their `user_id`.
3. They submit answers. They're verified again, and the run is loaded only if its `user_id` matches theirs.
4. If the resume fails, they can retry. They're verified again, and the failed run is loaded only if its `user_id` matches theirs.
5. R2 reads the finished output by run ID and `user_id`.

---

## C4. R1 Run Coordinator

### Goal of Component

One service runs a full R1 step around the store:

- **Start:** create a run ID → run the start part → save as paused or finished.
- **Resume:** load → save the answers → run the resume part → save as finished.
- **Retry:** load a failed, retryable run → run the resume part again on the saved state and saved answers → save as finished, or as failed again.

Any R1 error saves the run as failed with its stage.

### Problem It Aims to Solve

C1 knows R1 and C3 knows the database, but nothing ties them together into the status rules. Putting that in the HTTP layer would leave the rules untestable without a server.

**Traces to:** "save … under the run's ID", "save the answers to the same run", "one clear status", "run ID created when the run started".

### Mandatory Sub-Tasks Independent of Approaches Taken

- The run ID is created once, at start, and reused for every save afterwards.
- R1 errors map to `failed` together with `failure_stage`, taken from the error's `stage` attribute.
- Log events carry the run ID.

### Finalized Approach

**Run inside the request.**

| Approach | What the page experiences |
|---|---|
| Inside the request | The page sends the request and waits until R1 pauses or finishes, then gets the answer in the same response. |

### Finalized Decisions

- **What a failed run keeps:** its last state. "Save as failed" (C3) changes only the status, stage and message, so the saved state stays as it was.
- **Failure after resume:** the customer can retry from the saved answers (see below).

### Failure After Resume: Retry from Saved Answers

#### Goal

When R1 fails after the customer has answered, the customer can retry. The run continues from the saved state with their saved answers, so they don't retype their requirements or answer new questions.

#### Why It Works with Little New Code

- **Answers saved first:** C3's "Save the answers" writes the state, with the answers in `state.user_responses`, before resume runs.
- **Failure leaves the state alone:** C3's "Save as failed" changes only the status, stage and message.
- **Result:** after a failed resume, the row still holds a clean copy of the state from just before resume, with the answers already in it.

#### Retry Flow

1. The customer clicks **Retry** on the R1 page.
2. The page calls `POST /api/requirement-interpretation/runs/{run_id}/retry` with **no request body**.
3. The login check verifies the customer, and the run is loaded by `run_id` and `user_id`.
4. The coordinator checks that the run is `failed` and retryable. If not, the request is rejected.
5. The coordinator marks the retry as started.
6. The coordinator runs the resume steps on the saved state, using the saved answers.
7. The run is saved as `finished`, or as `failed` again.
8. The response has the same shape as the clarification-answers endpoint.

#### Rules

| Rule | Detail |
|---|---|
| **Answers can't change on a retry** | The retry endpoint takes no body. Answers come only from the saved state, so changing them is impossible. |
| **Separate endpoints, shared logic** | `/clarification-answers` always requires answers; `/retry` never takes any. Both call the same coordinator resume code. |
| **Never save the state partway through resume** | Only the finished state is written. The saved copy stays clean, with the pass counter at 1, so a retry runs the second router call exactly as the first attempt did. |
| **Retryable failures** | Failures after the answers were saved, where the LLM provider was unavailable or returned a bad body. A second call may succeed. |
| **Not retryable** | A state-version mismatch (C2 says start again), and failures in the start step, before or without a pause (there are no saved answers to reuse). |
| **No new status** | Statuses stay `needs_answers`, `finished`, `failed`. A retry moves `failed` → `finished`, or back to `failed`. |

#### Changes Required in Other Components

| Component | Addition |
|---|---|
| **C1** | Split resume so the steps after answer recording can run on their own, for example `continue_after_answers(state)`. `resume(state, answers)` records the answers and then calls it; retry calls it directly. `start` accepts the payload the coordinator has already checked, so the input check runs only once. |
| **C3** | The "never save the state partway through resume" rule. A `retryable` column set by "Save as failed", and an `attempts` column to enforce the retry limit of 1. |
| **C4** | The retry flow above and the rule for which failures can be retried. |
| **C5** | `POST /api/requirement-interpretation/runs/{run_id}/retry` with no request body, behind the same login check and `user_id` filter. Same response shape as the clarification-answers endpoint. Every failed response, including `502`/`503` bodies and the status endpoint, carries `retryable`. |
| **C6** | Test: a resume that fails, then a retry, gives the same final state as a resume that never failed, using the same fake LLM responses. Also test that `/retry` is rejected for runs that aren't retryable. |

### Finalized Retry Decisions

- **Telling the two kinds of `failed` apart:** the server decides whether a failed run can be retried and sends a `retryable` true/false flag. The page only reads the flag and never works it out itself.
  1. When the coordinator saves a run as `failed`, it also sets a `retryable` column on the row:
     - `true`: the failure happened after the answers were saved, and the cause was the LLM provider (unavailable, or it returned a bad body).
     - `false`: a state-version mismatch, any failure in the start step, or the retry limit has been reached.
  2. Every failed response includes the flag, including the `502`/`503` bodies and `GET .../runs/{run_id}`:
     `{ "run_id": "...", "status": "failed", "retryable": true }`
  3. The page shows **Retry** when the flag is `true` and **Start again** when it is `false`.
  4. The `/retry` endpoint checks the same flag and returns `409` when it is `false`.
- **Retry limit:** 1. A run can be retried once. If that retry fails, the run is saved with `retryable: false`.
- **How a retry is triggered:** manually, when the customer clicks Retry. There are no automatic retries.
- **Input check before the row is created:** the coordinator runs the check first, creates the row, then hands over to the rest of `start`.
  1. The coordinator calls `intake_and_assemble_payload`. If the input fails, R1's input error goes back as `422` and no run is created.
  2. If the input passes, the coordinator creates the run's row (C3).
  3. The coordinator hands the checked payload to `start`, so the input check runs only once.

---

## C5. HTTP Endpoints

### Goal of Component

The R1 page reaches C4 over HTTPS. It sends the requirements, receives either the questions or the result with the run ID and status, and sends the answers back.

### Problem It Aims to Solve

No deep-search routes exist, and the app's startup doesn't build R1 or its LLM caller.

**Traces to:** "separate requests over HTTPS", "return the clarification questions to the customer", "one clear status".

### Mandatory Sub-Tasks Independent of Approaches Taken

- At app startup, build the shared LLM caller, R1 and the store once; close the caller on shutdown.
- Request and response models for the four endpoints below.
- Map each outcome to the status codes in Finalized Decisions.
- Every failed response carries the `retryable` flag (C4), including the `502`/`503` bodies and the status endpoint: `{ "run_id": "...", "status": "failed", "retryable": true }`. The page shows **Retry** or **Start again** from this flag only.
- All four endpoints sit behind the existing login check (`get_authenticated_user`), and every run is read and written with the verified `user_id` (C3).
- Register the router in `main.py`.

### Finalized Approach

**Separate action endpoints under `/api/requirement-interpretation/runs`.**

| Purpose | Method and path | Request | Response |
|---|---|---|---|
| **Start** | `POST /api/requirement-interpretation/runs` | `{ "requirements": "<text>" }` | `run_id`, `status`, and `questions` or `result` |
| **Clarification answers** | `POST /api/requirement-interpretation/runs/{run_id}/clarification-answers` | One answer per question: the option number (1–5), plus a description when "other" is chosen | `run_id`, `status`, `result` |
| **Retry** | `POST /api/requirement-interpretation/runs/{run_id}/retry` | No body | `run_id`, `status`, `result` |
| **Status** (refresh recovery) | `GET /api/requirement-interpretation/runs/{run_id}` | None | `run_id`, `status`, and `questions` or `result` |

**What each endpoint calls:**
- **Start:** the coordinator's start flow (C4). The response carries `questions` when the run paused (`needs_answers`), or `result` when it finished.
- **Clarification answers:** the coordinator's resume flow (C4). The answer format is the one finalized in C1.
- **Retry:** the coordinator's retry flow (C4). It takes no body, so the answers can't change, and it returns the same response shape as the clarification-answers endpoint.
- **Status:** read-only. It uses the store's "load a run" operation (C3), never calls `start` or `resume`, makes no LLM calls and changes nothing.

### Finalized Decisions

- **Status recovery after a refresh:** kept, using `GET /api/requirement-interpretation/runs/{run_id}`.
  - **Nuance:** the page learns a run's status only from the HTTP reply, which lives in browser memory. A refresh wipes it, while the status stays saved in `r1_runs`.
  - **Approach:** when a reply arrives, the page saves its `run_id` in `sessionStorage`, not in the URL. After a refresh, it reads the `run_id` back and calls `GET /api/requirement-interpretation/runs/{run_id}`. The server returns the run's status and its questions or result from the row, filtered by the verified `user_id`, and the page shows it again.
  - **Limit:** `sessionStorage` is cleared when the tab closes, so a run started in a closed tab can't be recovered this way, and the customer starts again.

- **Status codes:**

  | Endpoint | Success | Errors |
  |---|---|---|
  | **Start:** `POST /api/requirement-interpretation/runs` | `201 Created`, since it creates a run. The body has `questions` (`needs_answers`) or `result` (`finished`). | `422` if the input fails R1's checks (no run is created). `502`/`503` if the LLM providers fail and the run is now `failed`; the body carries `run_id`, `status: failed` and `retryable: false`. |
  | **Clarification answers:** `POST /api/requirement-interpretation/runs/{run_id}/clarification-answers` | `200 OK` with `result` (`finished`). | `404` if the run isn't found or isn't this user's. `409` if the run isn't in `needs_answers`. `422` if the answers don't match the C1 format. `502`/`503` if the LLM providers fail; the body carries `run_id`, `status: failed` and `retryable`. |
  | **Retry:** `POST /api/requirement-interpretation/runs/{run_id}/retry` | `200 OK` with `result` (`finished`). | `404` if the run isn't found or isn't this user's. `409` if the run isn't `failed` or its `retryable` flag is `false`. `502`/`503` if the LLM providers fail again; the body carries `run_id`, `status: failed` and `retryable`. |
  | **Status:** `GET /api/requirement-interpretation/runs/{run_id}` | `200 OK` with the run's `status` and its `questions` or `result`, or `retryable` when the run failed. | `404` if the run isn't found or isn't this user's. |

- **URL versioning:** none.
- **What `result` shows the customer:** `category_metric_plans` from the finished state.

---

## C6. Verification of C1–C5

### Goal of Component

Evidence that C1–C5 work together as finalized:

- Splitting R1 changed nothing: same input and same answers give the same output.
- Every status, retry rule, status code and `user_id` check behaves as specified.
- A run survives a restart between its two steps.
- The `r1_runs` migration is safe to run again: if the table already exists, it isn't created a second time.
- The existing tests and sample runs still pass.

### Problem It Aims to Solve

The work changes the code around a finished, tested M2 and adds a store, a coordinator and four endpoints. Without checks, a subtle difference such as the pass counter, a missing `user_id` filter or a wrong `retryable` value would go unnoticed and only show up later in R2 or on the page.

**Traces to:** "without changing R1's current results", "without breaking the existing tests and sample runs", "at most once", "survives restarts", "one clear status", "only a finished output may be handed to R2".

### Changes from the Initial Version

The initial C6 covered parity only. It is extended to cover what C1–C5 finalized since:

- C2's version check;
- C3's `user_id` filter, `retryable` and `attempts` columns, and the finished-output read;
- C4's input check before row creation, failure rules and retry limit;
- C5's four endpoints, status codes and login check.

### Mandatory Sub-Tasks Independent of Approaches Taken

**Test enablers (built first)**

- **Separate live test folder:** `backend/tests_live/`, with its own `conftest.py` that loads the real settings (LLM keys, Supabase URL, service-role key, database URL). It can't sit under `tests/`, because `tests/conftest.py` sets `SUPABASE_URL` to `https://example.supabase.co` at import time, and environment variables override `.env`.
- **Dev Supabase project:** the tests run against a dev project, never production, with the `r1_runs` migration applied.
- **Real LLM provider with a recording wrapper:** the real `StructuredLLMCaller` (OpenAI/Groq), wrapped so a test can:
  - **record** every response from the real provider during the first path of a parity test;
  - **replay** the recorded responses to the second path, so both paths see the same LLM output and parity can be proven exactly;
  - **inject a failure** on a chosen call (raise the provider error), because a real provider can't be made to fail on demand. All other calls stay real.
- **Coordinator dependency:** C5 gets the coordinator through a FastAPI dependency, so HTTP tests can pass in one built on the real store and the wrapped real provider with `app.dependency_overrides`. This is the same pattern `test_login.py` uses for `get_supabase_client`.
- **Login cookie:** tests sign tokens with a test signing key (the existing `make_access_token_verifier` pattern), so no passwords are needed. The token's subject is the UUID of one of two dedicated test users in the dev project, given in the live settings. The second user is for cross-user checks.
- **Clean-up:** each test deletes the rows it created, filtered by its test users' `user_id`, so runs don't build up in the dev database.
- **Direct database connection for the migration check:** a test-only Postgres driver (`psycopg`) and a `SUPABASE_DB_URL` setting, because the Supabase table API can't run `CREATE TABLE`.

**Migration: the table is created once**

| Test | Passes when |
|---|---|
| Migration is safe to re-run | Applying the `r1_runs` migration to a database where the table already exists raises no error and changes nothing. The SQL uses `create table if not exists`, `create index if not exists`, and an RLS switch that is safe to repeat. |
| Existing rows are kept | Rows already in `r1_runs` are still there, unchanged, after the migration runs again. |
| One table only | After the repeat run, `r1_runs` exists once, with the expected columns. |
| App never creates tables | App startup and the store only read and write rows; no code path outside the migration creates or alters `r1_runs`. |

**C1: Resumable entry points**

| Test | Passes when |
|---|---|
| Pause parity | `interpret()` with scripted terminal answers (recording the real LLM responses) and start → save → load → resume with the same answers (replaying them) give the same final state. |
| No-pause parity | A run with no category flags gives the same final state through `start` as through `interpret()`, with the second path replaying the first path's real responses. |
| Answer recording | The new answer-recording method builds the same `UserResponse` entries as the terminal path, for an option number and for "other" with a description. |
| At most once | Resume and retry never call question generation, and the pass counter ends at 2. |

**C2: State serialization**

| Test | Passes when |
|---|---|
| Round trip | A paused state and a finished state come back equal after JSON and back, including int keys, the frozen `PayloadRecord` and `None` fields. |
| Version mismatch | Loading a state with a different version raises the typed error. |

**C3: Run store**

| Test | Passes when |
|---|---|
| Status transitions | Each store operation writes the expected status and columns in the real `r1_runs` table. |
| Failed keeps state | "Save as failed" changes only status, stage, message and `retryable`; the saved state is unchanged. |
| Finished output only | "Get the finished output" returns `category_metric_plans` for a finished run and nothing for any other status. |
| `user_id` filter | Every read and write for another user's run finds nothing. |
| Row-level security | The publishable key can't read or write `r1_runs`; only the service-role key can. |

**C4: Run coordinator**

| Test | Passes when |
|---|---|
| Input check first | Input that fails `intake_and_assemble_payload` creates no row. |
| Start | A run with flags is saved as `needs_answers` with its questions; one without is saved as `finished`. |
| Start failure | An injected LLM failure in the start step saves `failed` with `retryable: false`. |
| Answers saved first | When resume fails on an injected LLM failure, the row still holds the answers in `state.user_responses` and the pass counter at 1, with `retryable: true`. |
| Retry parity | A resume that fails on an injected failure, followed by a retry, gives the same final state as a resume that never failed, with both replaying the same recorded real responses. |
| Retry limit | After one retry, `attempts` is 1. If that retry fails, the run is saved with `retryable: false`. |
| Retry rejected | Retry is refused for a run that isn't `failed`, has `retryable: false`, or has a state-version mismatch (which is saved as `failed` with `retryable: false`). |
| Restart | Brand-new R1, coordinator and store objects between start and resume, sharing only the row in `r1_runs`, give the same final state. |

**C5: HTTP endpoints**

| Test | Passes when |
|---|---|
| Login required | Every endpoint returns `401` without a valid access-token cookie. |
| Start | `201` with `questions` (`needs_answers`) or `result` (`finished`); `422` for input that fails R1's checks; `502`/`503` with `retryable: false` on provider failure. |
| Clarification answers | `200` with `result`; `404` for another user's run; `409` when not `needs_answers`; `422` for answers that don't match the C1 format; `502`/`503` with `retryable` on provider failure. |
| Retry | `200` with `result`; `404` for another user's run; `409` when not `failed` or `retryable` is `false`; `502`/`503` with `retryable` on provider failure. |
| Status | `200` with `status` and `questions`, `result` or `retryable`; `404` for another user's run; it makes no LLM calls and changes nothing. |
| Result shape | `result` is `category_metric_plans`. |

**Regression**

- The existing suite passes, including the scripted-`input()` tests in `test_mechanism_2_clarification.py` and `test_deep_search_coordinator.py`.
- The existing R1 sample runs in `feature_sample_runs/` still run.

### Finalized Approach

**Real LLM providers and the real Supabase database, tested at the service and HTTP layers.**

- C1–C4 are tested directly against the real `StructuredLLMCaller` and the real Supabase store (dev project).
- C5 is tested over HTTP with `httpx.AsyncClient` and `ASGITransport` against the real FastAPI app, with the same real services passed in through `app.dependency_overrides`.
- The migration is tested against the dev database itself, so a second run is proven not to create the table again.
- Live LLM output varies between calls, so parity tests record the real responses on the first path and replay them on the second. Every response still comes from a real provider.
- Failures are injected on chosen calls, because a real provider can't be made to fail on demand.

### Finalized Decisions

- **Where tests live:**
  - All C1–C5 and migration tests in `backend/tests_live/`, with their own `conftest.py` and real settings.
  - They run with `pytest tests_live`, separately from the existing suite in `tests/`.
- **Which database:** a dev Supabase project, never production. Each test cleans up its own rows.
- **How states are compared:** through C2's JSON output, so the comparison is exact and doesn't depend on object identity.
- **Missing settings:** if the LLM keys, service-role key or database URL aren't set, the live tests are skipped with a message that names the missing setting, not failed.
- **Cost and time:** each full R1 run makes about 5–7 real LLM calls, and replayed paths make none. The suite makes real calls on every run, so it costs money and takes minutes, not seconds.
- **Login:** tokens are signed with a test key and carry the UUIDs of two dedicated test users in the dev project. Real sign-in is already covered by the existing auth tests.

---

## Review Check

- **Order:** C1 and C2 have no dependencies. C3 needs C2. C4 needs C1 and C3. C5 needs C4. C6 covers all of them. Nothing is left unconnected.
- **Run ownership:** handled in C3 by a `user_id` column, the existing login check on the R1 router and a `user_id` filter on every query.
- **Left out on purpose:** handling of unexpected answer states (removed after review), the "running" status and job queues (not in the problem statement; noted only as approaches), and editing R1's output before R2.



## Needs to be included
**Four choices where the spec was silent, from the plan’s list:**
A new run’s row starts as failed, not retryable, until it pauses or finishes.
Each answer identifies its question by category_id.
A non-R1 error saves the run as failed with stage unexpected.
run_explicit_category_resolution is removed; nothing called it any more.