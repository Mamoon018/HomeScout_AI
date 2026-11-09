# R1 over HTTP: Traceflow (Pause, Resume, Retry, Status)

## Context

**Why this document exists.** [R1_HTTP_Pause_Resume_Process_Flow.md](R1_HTTP_Pause_Resume_Process_Flow.md)
defines six components (C1–C6) that let a customer run R1 from a web page in one or two steps.
The plan describes each component on its own. This traceflow follows **one customer through the
four endpoints**, box by box, so you can see where each component acts, what data moves, and
where the flow can drift or break.

**What it covers.** The problem statement and the approach only: auth, endpoints, coordinator,
store, state, statuses, retry, refresh recovery. R1's decision logic (extraction, 2A, router, 2B,
inference, depth, metrics) is shown as single "black box" steps, because it is reused as-is.

**How to read it.** Every endpoint is traced as a chain of boxes. Every box has:

- `in:` what the box receives
- `do:` what the box does
- `exit:` every way the box can end, and where each exit goes

Each box is tagged with its **stage**, so you can follow one kind of concern across the flow.

> This is an understanding artifact. It is derived from the plan and does not change it.
> Points marked ⚠ are not settled by the plan; they are collected in Part 7.

### Legend

```
Stage tags
  [UA]    user action on the page                   [BIZ]   coordinator / R1 work (C1, C4)
  [AUTH]  login check (get_authenticated_user)      [DATA]  database read or write (C2, C3)
  [API]   FastAPI route, request model (C5)         [RESP]  HTTP response sent to the page
  [UA→]   what the user can do next with the response

Box shape
  ┌─ [TAG] ID · name ──────────     one step
  │ in:   ...                       what it receives
  │ do:   ...                       what it does
  │ exit: ✔ ... ──▶ next box        normal exit
  │       ✖ ... ──▶ response        failure exit
  └────────────────────────────     end of step

Markers
  LLM   the step makes a real LLM call (can fail, slow, costs money)
  ✅    the plan decides this point (component given)
  ⚠ Bn  not settled by the plan; see Part 7, breaking point Bn
```

---

## Part 1 — The whole customer journey on one page

This is the map. Parts 3–6 zoom into each arrow.

```
                    (customer is logged in: access-token cookie set by /auth/login)
                                             │
                                             ▼
   ┌───────────────────────── SCREEN A: Requirements input ─────────────────────────┐
   │  customer types free-text requirements, clicks Submit                         │
   └───────────────────────────────────────────┬────────────────────────────────────┘
                                               │  E1  POST /api/requirement-interpretation/runs
                                               ▼
                                  ┌─ SCREEN W: waiting (LLM work in request) ─┐
                                  └──┬──────────────┬──────────────┬──────────┘
                     422 input check │       201    │ 201          │ 502/503
                     (no run made)   │ needs_answers│ finished     │ failed, retryable:false
                        ▼            │              │              ▼
                 back to SCREEN A    │              │      SCREEN S: "Start again"
                 with the message    │              │      (back to SCREEN A)
                                     ▼              ▼
          ┌──── SCREEN Q: clarification questions ┐  ┌── SCREEN R: result ─────────┐
          │ one question per unclear category,     │  │ category_metric_plans       │
          │ options 1–5, "other" + description     │  │ (run is finished; R2 may    │
          └──────────────────┬─────────────────────┘  │  read it by run_id)         │
                             │                         └─────────────────────────────┘
                             │  E2  POST .../runs/{run_id}/clarification-answers
                             ▼                                      ▲
                 ┌─ SCREEN W: waiting ─┐                            │
                 └──┬───────────────┬──┘                            │
           200      │               │ 502/503 failed                │
           finished │               │                               │
                    ▼               ▼                               │
               SCREEN R      retryable:true ──▶ SCREEN F: "Retry"   │
                                                     │              │
                                                     │ E3 POST .../runs/{run_id}/retry (no body)
                                                     ▼              │
                                          ┌─ SCREEN W: waiting ─┐   │
                                          └──┬───────────────┬──┘   │
                                     200     │               │ 502/503 failed,
                                     finished└───────────────┼──────┘ retryable:false
                                                             ▼
                                                      SCREEN S: "Start again"

   At any time:  page refresh  ──▶ E4 GET .../runs/{run_id}  (run_id from sessionStorage)
                 ──▶ re-renders SCREEN Q, R, F or S from the saved row. Nothing is changed.
```

**Run status as the customer sees it** (`r1_runs.status`, C3): only three values exist,
`needs_answers`, `finished`, `failed`. The page picks the screen from `status` and, for
`failed`, from `retryable` only. The page never decides retryability itself. ✅ C4

---

## Part 2 — Shared gate used by all four endpoints

Every endpoint passes through the same two boxes before any R1 work.

```
┌─ [AUTH] G1 · Verify login cookie ─────────────────────────────────── existing ──
│ in:   request cookie (ACCESS_TOKEN_COOKIE_POLICY.name, path "/")
│ do:   get_authenticated_user → AccessTokenVerifier.verify(token)
│       requires email + user_name claims
│ exit: ✔ AuthenticatedUser{user_id = token subject} ──▶ G2
│       ✖ missing / invalid cookie      ──▶ 401 {"error":"Not authenticated"}
│       ✖ expired token                 ──▶ 401 {"error":..., "code":"token_expired"}
│ ✅ C3 Layer 1 (router-level Depends, same as /api/user_welcome)
│ ⚠ B1 page must refresh the session and resend the SAME request on token_expired
└──────────────────────────────────────────────────────────────────────────────────

┌─ [API] G2 · Route + request model ─────────────────────────────────────── C5 ──
│ in:   path run_id (E2, E3, E4), JSON body (E1, E2), verified user_id
│ do:   FastAPI parses the body into the request model
│       coordinator is injected as a FastAPI dependency (built once at startup)
│ exit: ✔ typed request + user_id ──▶ endpoint's first [BIZ]/[DATA] box
│       ✖ body shape wrong          ──▶ 422 (FastAPI validation)
│ ✅ C5 (router registered in main.py; lifespan builds LLM caller, R1, store)
│ RULE  user_id comes from G1 only, never from the body or the path ✅ C3 Layer 2
└──────────────────────────────────────────────────────────────────────────────────
```

---

## Part 3 — E1 · Start a run

**Purpose.** Turn the customer's free text into either the clarification questions (pause) or
the finished R1 result (no pause), and create the run that both steps share.

**Trigger.** On SCREEN A the customer types requirements and clicks Submit.

**Endpoint.** `POST /api/requirement-interpretation/runs` · body `{ "requirements": "<text>" }`

```
┌─ [UA] E1.0 · Submit requirements ───────────────────────────────────────────────
│ in:   free text typed on SCREEN A
│ do:   page disables Submit, shows SCREEN W, sends POST with credentials (cookie)
│ exit: ✔ request sent ──▶ G1 ──▶ G2
│ ⚠ B2 no run_id exists yet; a refresh or tab close now loses the run on the page
│ ⚠ B3 double-click / resend creates a second run (no idempotency key)
└──────────────────────────────────────────────────────────────────────────────────
        │ requirements, user_id
        ▼
┌─ [BIZ] E1.1 · Input check (no LLM) ──────────────────────────────── C4 → R1 ──
│ in:   requirements text
│ do:   R1.intake_and_assemble_payload(raw_input)
│       normalise text → word-count bound → is_english
│ exit: ✔ PayloadRecord (frozen) ──▶ E1.2
│       ✖ InputTooShortError / UnsupportedLanguageError
│              ──▶ 422 with R1's message. NO run_id, NO row.  ──▶ SCREEN A
│ ✅ C4 "input check before the row is created"; C3 "when the row is created"
└──────────────────────────────────────────────────────────────────────────────────
        │ PayloadRecord
        ▼
┌─ [DATA] E1.2 · Create the run ─────────────────────────────────────────── C3 ──
│ in:   new run_id (created ONCE here), user_id, PayloadRecord
│ do:   INSERT r1_runs { run_id, user_id, attempts:0, created_at, updated_at, ... }
│       async Supabase client, service-role key
│ exit: ✔ row exists ──▶ E1.3
│       ✖ database error ──▶ ⚠ B9 (no mapping in the plan)
│ ✅ C4 "run ID is created once, at start, and reused"
│ ⚠ B4 the row's status between INSERT and the first save is not defined
│       (only needs_answers / finished / failed exist)
└──────────────────────────────────────────────────────────────────────────────────
        │ run_id, PayloadRecord
        ▼
┌─ [BIZ] E1.3 · R1 start part ──────────────────────────────────── C1 start() ──
│ in:   PayloadRecord (input check is NOT re-run)
│ do:   extraction                                         LLM
│       2A pass 1 (resolve_explicit_categories)            LLM
│       router (inspect_category_resolution, pass 1)
│       ├─ no category flags ──▶ finish part:
│       │     inference                                    LLM
│       │     depth                                        LLM
│       │     metrics                                      LLM
│       │     status = finished
│       └─ category flags ──▶ question generation          LLM
│             questions stored on state (new optional field)
│             status = needs_answers   (STOP here; no input())
│ exit: ✔ (needs_answers, state with questions) ──▶ E1.4a
│       ✔ (finished, final state)                ──▶ E1.4b
│       ✖ typed R1 error with .stage             ──▶ E1.4c
│ ✅ C1 "two explicit methods", "status plus state"
│ ⚠ B5 the whole step runs inside the HTTP request (≈3–7 LLM calls)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ├──────────────────────────────┬──────────────────────────────┐
        ▼                              ▼                              ▼
┌─ [DATA] E1.4a · Save as paused ┐ ┌─ [DATA] E1.4b · Save finished ┐ ┌─ [DATA] E1.4c · Save failed ─┐
│ in:  state (+questions)        │ │ in:  final state               │ │ in:  R1 error                │
│ do:  UPDATE one row:           │ │ do:  UPDATE one row:           │ │ do:  UPDATE one row:         │
│      status = needs_answers    │ │      status = finished         │ │      status = failed         │
│      state  = C2 JSON + version│ │      state  = C2 JSON          │ │      failure_stage = .stage  │
│                                │ │      output = category_        │ │      failure_message         │
│                                │ │               metric_plans     │ │      retryable = false       │
│                                │ │                                │ │      state untouched         │
│ exit: ✔ ──▶ E1.5a              │ │ exit: ✔ ──▶ E1.5b              │ │ exit: ✔ ──▶ E1.5c            │
│ ✅ C2, C3                      │ │ ✅ C3 (output column for R2)   │ │ ✅ C4 start failure = never  │
│ ⚠ B9 if this write fails       │ │ ⚠ B9 if this write fails       │ │    retryable                 │
└────────────────────────────────┘ └────────────────────────────────┘ └──────────────────────────────┘
        │                              │                              │
        ▼                              ▼                              ▼
┌─ [RESP] E1.5a ─────────────────┐ ┌─ [RESP] E1.5b ─────────────────┐ ┌─ [RESP] E1.5c ───────────────┐
│ 201 { run_id,                  │ │ 201 { run_id,                  │ │ 502 / 503 { run_id,          │
│       status:"needs_answers",  │ │       status:"finished",       │ │   status:"failed",           │
│       questions:[...] }        │ │       result: category_        │ │   retryable:false }          │
│                                │ │               metric_plans }   │ │ ⚠ B10 502 vs 503 rule        │
└────────────────────────────────┘ └────────────────────────────────┘ └──────────────────────────────┘
        │                              │                              │
        ▼                              ▼                              ▼
┌─ [UA→] E1.6 · What the page does with the reply ────────────────────────────────
│ always: save run_id in sessionStorage (not in the URL)          ✅ C5
│ needs_answers ──▶ SCREEN Q (render questions, options 1–5, "other" text box)
│ finished      ──▶ SCREEN R (render category_metric_plans)
│ failed        ──▶ SCREEN S "Start again" (retryable is false)  ⚠ B11 retype text
└──────────────────────────────────────────────────────────────────────────────────
```

**E1 exits at a glance**

| Exit | HTTP | Row after it | Screen next |
|---|---|---|---|
| Not logged in / token expired | 401 | none | login, or refresh then resend |
| Body malformed | 422 | none | SCREEN A |
| Input too short / not English | 422 | none | SCREEN A |
| Paused for questions | 201 | `needs_answers`, state + questions | SCREEN Q |
| Finished without questions | 201 | `finished`, state + output | SCREEN R |
| LLM failure in start | 502/503 | `failed`, `retryable:false` | SCREEN S |
| Database failure | ⚠ B9 | ⚠ B4 / B9 | ⚠ |

---

## Part 4 — E2 · Submit clarification answers

**Purpose.** Save the customer's answers to the same run, then continue R1 from the saved
state (never from the beginning) until it finishes.

**Trigger.** On SCREEN Q the customer picks one option (1–5) per question, types a description
when "other" is chosen, and clicks Submit.

**Endpoint.** `POST /api/requirement-interpretation/runs/{run_id}/clarification-answers`
· body: one answer per question, `{ option: 1–5, description?: "<text when other>" }`

```
┌─ [UA] E2.0 · Submit answers ────────────────────────────────────────────────────
│ in:   chosen options (+ "other" text), run_id from the E1 reply / sessionStorage
│ do:   page disables Submit, shows SCREEN W, sends POST with cookie
│ exit: ✔ request sent ──▶ G1 ──▶ G2
│ ⚠ B1 if 401 token_expired, the page must keep the answers and resend after refresh
│ ⚠ B6 double-click / second tab sends a second resume for the same run
└──────────────────────────────────────────────────────────────────────────────────
        │ run_id, answers, user_id
        ▼
┌─ [DATA] E2.1 · Load the run ──────────────────────────────────────── C3 + C2 ──
│ in:   run_id, user_id
│ do:   SELECT r1_runs WHERE run_id = ? AND user_id = ?
│       C2: JSON → RequirementInterpretationState (TypeAdapter), check version
│ exit: ✔ status, retryable, attempts, state ──▶ E2.2
│       ✖ no row / other user's row      ──▶ 404 (same answer for both)
│       ✖ state version ≠ code version   ──▶ save failed, retryable:false
│                                             ──▶ ⚠ B7 (HTTP code not in the table)
│ ✅ C3 user_id filter on every read; C2 "reject the run" on version mismatch
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] E2.2 · Status guard ────────────────────────────────────────────── C4 ──
│ in:   loaded status
│ do:   require status == needs_answers
│ exit: ✔ ──▶ E2.3
│       ✖ finished / failed ──▶ 409  (page should call E4 to resync)
│ ✅ C5 status codes
│ ⚠ B6 the check and the later writes are separate steps; two requests that
│       both read needs_answers both pass (no compare-and-set, no "running" status)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] E2.3 · Check answers against the saved questions ──────────────── C1 ──
│ in:   answers, state.questions (saved in E1.4a)
│ do:   one answer per question; option in 1–5; description present when "other"
│ exit: ✔ ──▶ E2.4
│       ✖ mismatch ──▶ 422  (nothing written)
│ ✅ C1 answer format; C5 422
│ ⚠ B8 the plan does not say this runs before E2.5 (it must, or bad answers get saved)
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] E2.4 · Record answers (no LLM) ────────────────── C1 answer-recording ──
│ in:   raw answers, state
│ do:   build UserResponse per question:
│       chosen option's text, or the customer's description for "other"
│       → state.user_responses   (same method the terminal path uses)
│ exit: ✔ state with answers ──▶ E2.5
│ ✅ C1 "where answers become UserResponse entries"
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [DATA] E2.5 · Save the answers (BEFORE resume) ───────────────────────── C3 ──
│ in:   state with answers, pass counter = 1
│ do:   UPDATE one row: state = C2 JSON (answers inside state.user_responses)
│       status stays needs_answers  (⚠ B6: not stated in the plan)
│ exit: ✔ ──▶ E2.6
│       ✖ database error ──▶ ⚠ B9
│ ✅ C3 "save the answers"; C4 "answers saved first" — this copy is what retry reuses
└──────────────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ [BIZ] E2.6 · Continue after answers ─────────────── C1 continue_after_answers ──
│ in:   state with answers (in memory only)
│ do:   2B resolve_category_flags (2A pass 2 using the answers)   LLM
│       router (pass 2; counter → 2, no new questions)
│       inference                                                  LLM
│       depth                                                      LLM
│       metrics                                                    LLM
│       NEVER calls question generation                            ✅ "at most once"
│       NEVER writes the state partway                             ✅ C3 rule
│ exit: ✔ final state ──▶ E2.7a
│       ✖ provider unavailable / bad body ──▶ E2.7b
│ ⚠ B5 runs inside the HTTP request
└──────────────────────────────────────────────────────────────────────────────────
        │
        ├───────────────────────────────────────┐
        ▼                                       ▼
┌─ [DATA] E2.7a · Save as finished ───┐  ┌─ [DATA] E2.7b · Save as failed ─────────┐
│ status = finished                   │  │ status = failed                         │
│ state  = final state (C2 JSON)      │  │ failure_stage, failure_message          │
│ output = category_metric_plans      │  │ retryable = true                        │
│                                     │  │ state UNTOUCHED (the E2.5 copy, counter │
│                                     │  │ at 1, answers inside)                   │
│ ✅ C3                                │  │ ✅ C4 "retryable failures"              │
└─────────────────────────────────────┘  └─────────────────────────────────────────┘
        │                                       │
        ▼                                       ▼
┌─ [RESP] E2.8a ──────────────────────┐  ┌─ [RESP] E2.8b ──────────────────────────┐
│ 200 { run_id, status:"finished",    │  │ 502 / 503 { run_id, status:"failed",    │
│       result }                      │  │             retryable:true }            │
└─────────────────────────────────────┘  └─────────────────────────────────────────┘
        │                                       │
        ▼                                       ▼
┌─ [UA→] E2.9 ────────────────────────────────────────────────────────────────────
│ finished ──▶ SCREEN R
│ failed + retryable:true ──▶ SCREEN F with a Retry button (──▶ E3)
└──────────────────────────────────────────────────────────────────────────────────
```

**E2 exits at a glance**

| Exit | HTTP | Row after it | Screen next |
|---|---|---|---|
| Not logged in / token expired | 401 | unchanged | login, or refresh then resend |
| Run missing or another user's | 404 | unchanged | SCREEN S |
| State version mismatch | ⚠ B7 | `failed`, `retryable:false` | SCREEN S |
| Run not `needs_answers` | 409 | unchanged | resync with E4 |
| Answers don't fit the questions | 422 | unchanged | SCREEN Q |
| Finished | 200 | `finished`, state + output | SCREEN R |
| LLM failure in resume | 502/503 | `failed`, `retryable:true`, state = answers copy | SCREEN F |

---

## Part 5 — E3 · Retry after a failed resume

**Purpose.** Let the customer finish a run whose resume failed on the LLM provider, using the
answers already saved. No retyping, no new questions, answers cannot change.

**Trigger.** On SCREEN F (`failed`, `retryable:true`) the customer clicks Retry.

**Endpoint.** `POST /api/requirement-interpretation/runs/{run_id}/retry` · no body

```
┌─ [UA] E3.0 · Click Retry ───────────────────────────────────────────────────────
│ in:   run_id (sessionStorage)
│ do:   POST with cookie, no body; SCREEN W
│ exit: ✔ ──▶ G1 ──▶ G2
│ ⚠ B6 double-click sends two retries
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] E3.1 · Load the run ──────────────────────────────────────── C3 + C2 ──
│ do:   SELECT by run_id + user_id; C2 decode + version check
│ exit: ✔ ──▶ E3.2      ✖ 404      ✖ version mismatch ──▶ failed, retryable:false, ⚠ B7
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] E3.2 · Retry guard ─────────────────────────────────────────────── C4 ──
│ in:   status, retryable, attempts
│ do:   require status == failed AND retryable == true  (attempts < 1 implied)
│ exit: ✔ ──▶ E3.3
│       ✖ otherwise ──▶ 409
│ ✅ C4 rules, limit = 1
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] E3.3 · Mark retry started ─────────────────────────────────────── C3 ──
│ do:   UPDATE attempts = attempts + 1   (status still failed)
│ exit: ✔ ──▶ E3.4
│ ⚠ B6 not atomic with E3.2: two retries can both read attempts = 0
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [BIZ] E3.4 · Continue after answers (same code as E2.6) ─────────────── C1 ──
│ in:   SAVED state from E2.5: answers inside, pass counter = 1
│ do:   2B → router pass 2 → inference → depth → metrics                LLM ×4+
│       answers are NOT recorded again (they are already in the state)
│ exit: ✔ final state ──▶ save finished ──▶ 200 { run_id, finished, result } ──▶ SCREEN R
│       ✖ provider failure ──▶ save failed, retryable:false (limit reached)
│                           ──▶ 502/503 { run_id, failed, retryable:false } ──▶ SCREEN S
│ ✅ C4 retry flow; C6 "retry parity" (same final state as a resume that never failed)
└──────────────────────────────────────────────────────────────────────────────────
```

---

## Part 6 — E4 · Status (refresh recovery)

**Purpose.** After a page refresh, show the customer the screen that matches the saved run,
without doing any work.

**Trigger.** The page loads and finds a `run_id` in `sessionStorage`.

**Endpoint.** `GET /api/requirement-interpretation/runs/{run_id}`

```
┌─ [UA] E4.0 · Page load ─────────────────────────────────────────────────────────
│ do:   read run_id from sessionStorage
│ exit: ✔ found ──▶ GET ──▶ G1 ──▶ G2
│       ✖ not found (new tab, tab was closed) ──▶ SCREEN A   ✅ C5 "limit"
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [DATA] E4.1 · Load the run (read-only) ──────────────────────────── C3 + C2 ──
│ do:   SELECT by run_id + user_id; decode state
│       NO LLM calls, NO writes                                 ✅ C5
│ exit: ✔ ──▶ E4.2     ✖ 404 ──▶ clear sessionStorage ──▶ SCREEN A
│ ⚠ B7 version mismatch: C2 says "mark failed", C5 says "changes nothing"
└──────────────────────────────────────────────────────────────────────────────────
        ▼
┌─ [RESP] E4.2 · Reply by status ──────────────────────────────────────── C5 ──
│ needs_answers ──▶ 200 { run_id, status, questions }        ──▶ SCREEN Q
│ finished      ──▶ 200 { run_id, status, result }           ──▶ SCREEN R
│ failed        ──▶ 200 { run_id, status, retryable }        ──▶ SCREEN F or S
│ ⚠ B6 during an E2 still in flight, this returns needs_answers + questions,
│       so the page invites the customer to answer again
│ ⚠ B4 a row caught between INSERT and its first save has no defined status
└──────────────────────────────────────────────────────────────────────────────────
```

---

## Part 7 — The run row: lifecycle and data actions

### 7.1 Status lifecycle

```
   (no row) ── E1.1 input fails ──▶ (still no row)                       422
      │
      │ E1.2 INSERT                 ⚠ B4 status here?
      ▼
   [created] ──E1.4a──▶ needs_answers ──E2.5──▶ needs_answers (+answers) ──E2.7a──▶ finished
      │                                                │
      ├──E1.4b──────────────────────────────────────── │ ───────────────────────▶ finished
      │                                                │
      └──E1.4c──▶ failed (retryable:false)             └──E2.7b──▶ failed (retryable:true)
                                                                       │
                                                                 E3.3 attempts = 1
                                                                       │
                                                       ┌───────────────┴───────────────┐
                                                       ▼                               ▼
                                                   finished                 failed (retryable:false)

   Version mismatch on any load (E2.1, E3.1) ──▶ failed (retryable:false)
   finished is terminal. failed + retryable:false is terminal ("Start again" = new run).
```

### 7.2 Data actions per endpoint, in order

| # | Endpoint | Store operation (C3) | Columns written | When |
|---|---|---|---|---|
| 1 | E1 | Create a run | `run_id`, `user_id`, `attempts=0`, timestamps | after input check, before LLM |
| 2 | E1 | Save as paused | `status=needs_answers`, `state` (+questions, version) | R1 paused |
| 2' | E1 | Save as finished | `status=finished`, `state`, `output` | no flags |
| 2'' | E1 | Save as failed | `status=failed`, `failure_*`, `retryable=false` | LLM error |
| 3 | E2 | Load a run | — (read) | first |
| 4 | E2 | Save the answers | `state` (answers inside) | before resume |
| 5 | E2 | Save as finished | `status=finished`, `state`, `output` | resume ok |
| 5' | E2 | Save as failed | `status=failed`, `failure_*`, `retryable=true` | resume LLM error |
| 6 | E3 | Load a run | — (read) | first |
| 7 | E3 | Mark retry started | `attempts+1` | before resume |
| 8 | E3 | Save as finished / failed | as 5 / 5' but `retryable=false` on failure | after resume |
| 9 | E4 | Load a run | — (read) | only action |
| 10 | R2 | Get the finished output | — (read `output` where `status=finished`) | later, outside R1 |

Every write is a single-row UPDATE filtered on `run_id` **and** `user_id`. ✅ C3

### 7.3 LLM calls per path (cost and wait time on SCREEN W)

| Path | LLM steps inside the request |
|---|---|
| E1, no flags | extraction, 2A, inference, depth, metrics (≈5+) |
| E1, flags | extraction, 2A, question generation (≈3) |
| E2 | 2B, inference, depth, metrics (≈4+) |
| E3 | same as E2 |
| E4 | none |

---

## Part 8 — Breaking points and drift register

Each point names the box where it shows up, what goes wrong, and whether the plan covers it.
They are grouped by level so you can think about each one at the right altitude.

### 8.1 Product level (what the customer experiences)

| ID | Box | What can go wrong | Plan coverage |
|---|---|---|---|
| B2 | E1.0 | `run_id` reaches the page only with the reply. A refresh or tab close during the start request leaves the page with nothing to recover; the run finishes on the server but is orphaned, and the customer starts again. | ⚠ open (C5 limit covers closed tabs only after a reply) |
| B11 | E1.6 | A start failure is never retryable, so the customer must retype the requirements unless the page keeps the text. | ⚠ open (page-side choice) |
| B12 | E4.2 | After a refresh on SCREEN Q the questions come back, but the customer's earlier selections do not (nothing is saved until E2). | ✅ acceptable by design; note only |
| B13 | Part 7.1 | Paused runs that are never answered stay `needs_answers` forever; no expiry or clean-up. | ⚠ open (not in problem statement) |
| B14 | SCREEN R | The result is shown, but nothing in R1's endpoints starts R2. Who triggers R2, and when, is outside these four endpoints. | ✅ out of scope (C3 only exposes the read) |
| B15 | E1.6 / E4 | One run per tab. A customer has no way to list or reopen earlier runs. | ✅ out of scope |

### 8.2 Technical level (what the code must handle)

| ID | Box | What can go wrong | Plan coverage |
|---|---|---|---|
| B1 | G1 | A `token_expired` 401 on E2 means the page must call `/auth/refresh` and resend the same answers. If the page drops them, the customer re-answers. Verification happens once at request start, so a token expiring mid-LLM-call is not a problem. | ⚠ page behaviour not written |
| B4 | E1.2 | The row is inserted before R1 runs, but no status is defined for it until the first save. A crash, deploy or timeout between the two leaves a row that E4 cannot render. | ⚠ open: pick an initial status or insert together with the first save |
| B7 | E2.1 / E3.1 / E4.1 | A version mismatch is "saved as failed" (C2), but no HTTP code is set for E2/E3, and E4 is defined as "changes nothing". | ⚠ open: which code, and whether E4 writes |
| B8 | E2.3 | The plan does not say answers are checked against the saved questions before "Save the answers". If the order is reversed, invalid answers become the saved copy that retry reuses. | ⚠ ordering not stated |
| B9 | E1.2, E1.4*, E2.5, E2.7* | Database failures are not mapped. Examples: "Save as finished" fails after R1 succeeded (result lost, row stays `needs_answers`); "Save as failed" itself fails (row keeps the previous status). | ⚠ open: HTTP code, retryable, and what the row shows |
| B10 | E1.5c, E2.8b | The rule that chooses 502 vs 503 is not written. | ⚠ open (suggested: 503 provider unavailable / breaker open, 502 bad body) |
| B16 | E1.3, E2.6 | Hosting or proxy timeouts (often 30–100 s) may cut the connection while R1 still runs. The server usually finishes and saves, but the page gets an error. For E2/E3 the page can recover with E4; for E1 it cannot (B2). | ⚠ depends on hosting; ties to B5 |
| B17 | E2.2 | 409 after a successful but lost reply (e.g. timeout then resend) looks like an error to the customer, though the run is `finished`. | ⚠ page should call E4 on 409 |

### 8.3 Architectural level (how the pieces fit)

| ID | Box | What can go wrong | Plan coverage |
|---|---|---|---|
| B5 | E1.3, E2.6, E3.4 | All R1 work runs inside the request. Wait time, timeouts and cost are tied to one HTTP connection, and there is no `running` status to show progress or block duplicates. | ✅ chosen (C4 "run inside the request"); consequences are B2, B6, B16 |
| B6 | E2.2→E2.5, E3.2→E3.3, E4.2 | Guards and writes are separate steps, and during E2 the row still says `needs_answers`. Two answer submissions (double-click, second tab, refresh + resubmit) or two retries can both pass the guard, both run R1, and the last write wins. Retry can exceed the limit of 1. | ⚠ open: conditional updates (`... WHERE status = 'needs_answers'` / `WHERE attempts = 0`) or a claim column |
| B3 | E1.0 | Repeated start requests create separate runs; there is no idempotency key. | ⚠ open (low impact: extra rows and cost) |
| B18 | C3 | The service-role key bypasses row-level security. Isolation between users depends entirely on the backend adding `user_id` to every query. | ✅ accepted trade-off (C3); C6 tests the filter |
| B19 | C2 | The saved state is tied to the code version. Any deploy that changes the state shape fails every paused run in flight. | ✅ accepted (C2 "reject the run") |
| B20 | lifespan | Several workers or instances are fine because all run state is in `r1_runs`; anything kept in process memory (LLM caller, circuit breaker) is per worker. | ✅ no shared in-memory state needed |

### 8.4 Where to look first

The open points that can corrupt or lose a run, rather than only annoy the customer, are:

1. **B6** concurrent resume / retry (two writers on one row).
2. **B4** the row's status between INSERT and the first save.
3. **B9** database failures after R1 succeeded.
4. **B8** answer check before "Save the answers".
5. **B7** version mismatch response and whether E4 writes.

The rest are product or page-behaviour choices that can be settled without changing C1–C5.
