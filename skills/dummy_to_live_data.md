---
name: dummy-to-live-data
description: Use when a frontend screen that was built against dummy data must be connected to its real backend endpoints. Drives a gated, step-by-step swap — contract, gap table, service layer, normalizer, state machine, failure states, presentation maps, tests, cleanup — so the screen keeps its look while handling every response the live endpoints can actually return: other statuses, missing or empty fields, slow responses, failures, retries, conflicts, and refreshes. Not for designing new UI or new endpoints.
---

# Dummy-to-Live Data Swap

An agent uses this skill when a screen already renders correctly from dummy data and now has to render from live endpoints. The screen's design is settled. What changes is everything the dummy data hid: real responses arrive late, arrive in other shapes depending on the run's status, arrive with empty or missing fields, fail, conflict, and get lost on refresh.

The discipline in one line:

> **Dummy data is one frozen, happy response. Live data is every response the endpoint can produce, over time. Enumerate those responses from the backend code, decide what the screen shows for each one, and only then write the swap.**

---

## Core principle: the response space, not the sample

The dummy file shows one point in the response space: one status, every field filled, delivered instantly. The live endpoint has a whole space, along four axes:

| Axis | What varies | Where you learn it |
| --- | --- | --- |
| **Status** | Which top-level fields are present (e.g. `questions` only while paused, `result` only when finished) | The backend view/response builder, per status |
| **Fill** | Lists that can be empty, fields that can be null or absent, enum values the dummy never used | The backend schema types and the serializer's options (e.g. `exclude_none`) |
| **Time** | How long the call takes, whether the work runs inside the request or in the background | The route/controller: sync vs `202` + polling |
| **Failure** | Every non-2xx code, its body, and what the user can do next (retry, start again, fix input, sign in) | The controller's error mapping and the typed errors behind it |

Every step below exists to cover one of these axes. A step that does not cover a real point in this space for **this** endpoint is skipped, with a one-line reason.

Three rules hold throughout:

1. **The backend code is the contract, not the sample file.** Samples show what happened once; the code shows what can happen.
2. **The backend is finalized.** Its endpoints, contracts and serialization are fixed for this process and are not changed. Every gap between the backend and the UI is absorbed on the frontend: in the types, the service layer, the normalizer or the hook.
3. **Components stay untouched.** Live-data handling lives in the service, normalizer and hook layers. If a component has to change, that is a finding to record, not a silent edit.

---

## Step 1 — Write the contract from the backend code

**Do:** For every endpoint the screen will call, write one contract entry.

**How:** Read the route, the controller, the response model and the code that builds the response. Do not read the sample first.

For each endpoint record:

- Method, path (relative, same-origin), path params, request body shape and its validation rules (min/max, required-unless, forbidden-unless).
- Whether the work runs **inside the request** (the call blocks until done) or **in the background** (`202` + a status endpoint to poll). Estimate the worst-case duration from what it calls (LLM calls, external APIs).
- The success code and, **per status value**, which top-level fields are present.
- For each field: type, whether it can be `null`, absent, or an empty list, and the full enum set.
- How the response is serialized: does it drop `None` (`exclude_none`)? At top level only, or nested too?
- Every error code the controller can return, the body shape, and what each one means for the user.

**Output:** A contract table per endpoint, plus a status table:

| Status | Fields present | Fields absent | User can do |
| --- | --- | --- | --- |

**Done when:** every status and every error code in the controller appears in the tables, and each row cites the file and line it came from.

---

## Step 2 — Inventory what the screen reads

**Do:** List every field the UI reads from the dummy data, and how it uses it.

**How:** Start from the page component's dummy imports and follow each prop down into the components. For each read, note:

- The field path (e.g. `extraction.ambiguity_flags[].category`).
- How it is used: shown as text, counted, mapped over, used as a key, used to pick an icon/color, used in a condition.
- What it does with an empty or missing value today (most dummy-built UIs never handle it).
- Which UI state (phase/step) it is shown in.

Also list every **timer, fake delay or hard-coded flag** in the hooks that stands in for backend progress (e.g. `setTimeout` to move from "extracting" to "done", a `hasQuestions` boolean). These are data too: they are the dummy version of status and time.

**Output:** A read inventory and a list of fake-progress mechanisms.

**Done when:** every dummy import and every timer in the screen's hooks is accounted for.

---

## Step 3 — Build the gap table (differences only)

**Do:** Compare Step 1 with Step 2 and record only the differences.

**How:** For each read in Step 2, check it against the contract. A row is needed when any of these is true:

| Gap type | Example |
| --- | --- |
| Name or path differs | UI reads `name`, API sends `display_name` |
| Type differs | UI expects `string`, API sends `number` |
| Nullability differs | UI type says `string \| null`, API omits the key entirely |
| Enum is wider | UI type allows 2 values, backend allows 3 |
| Field only exists in some statuses | UI reads `result` while the run is still paused |
| Empty is possible | UI maps over a list the backend can send empty |
| Request shape differs | UI always sends a field the backend rejects unless a condition holds |
| Timing differs | UI reveals data in stages; the API returns it all at once at the end |

For each row decide **where** on the frontend it gets absorbed (rule 2: the backend is not an option):

| Owner | Use it when |
| --- | --- |
| **Frontend type** | The UI type is simply wrong about the contract (a wider enum, a field that can be absent). Correct the type to match the backend. |
| **Service layer** | The gap is in the request (conditional fields, body shape) or the transport (timeout). |
| **Normalizer** | The response shape differs from what components read (absent vs `null`, missing lists, renamed paths). |
| **Hook** | The gap is about status or time (fields only present in some statuses, data arriving all at once). |
| **Component** | Only when the component itself cannot render a real value (e.g. an empty list). Record it per rule 3. |

**Output:** The gap table with a "fixed in" column.

**Done when:** each row has exactly one owner. If the table is empty, say so: the normalizer in Step 5 is then skipped.

---

## Step 4 — Write the service layer

**Do:** One function per endpoint, in `features/<feature>/api/`.

**How:**

- Use the app's existing API client (the one that already handles credentials and auth refresh). Use **relative, same-origin paths**. Do not add a base-URL environment variable when the dev proxy and cookie policy rely on same origin.
- Set the **timeout per call** from Step 1's worst-case duration. A call that runs LLM work inside the request needs a longer timeout than the client default; name it as a constant next to the function.
- Build request bodies exactly to the contract, including conditional fields (send a field only when the backend allows it).
- Return a typed result that separates: success body, error body with status code, timeout, network failure. Do not throw for expected HTTP errors; the hook decides what each one means.
- No UI logic and no state here.

**Output:** The service functions and their typed results.

**Done when:** every endpoint in Step 1 has one function, and every error code in Step 1 can be told apart from the result.

---

## Step 5 — Write one normalizer (only for the gaps that remain)

**Do:** A single `normalize<Entity>()` that turns the API body into the exact type the components already use.

**How:**

- Handle only the rows from Step 3 whose owner is "normalizer". Gaps owned by the types, the service layer or the hook do not belong here.
- Normalize the backend's serialization quirks here, once: for example, a field the backend omits when it is `None` becomes `null` (or `[]` for lists), so components never have to check for `undefined`.
- Keep it a pure function: no fetching, no state, no defaults that invent data. Missing-but-optional becomes `null` or `[]`; it never becomes a fake value.
- Unknown enum values are kept and flagged for the fallback in Step 8, never dropped silently.
- If a required field is missing, return an error result. Do not render a half-built object as if it were complete.

**Output:** The normalizer, or a one-line note that it is not needed because the types already match.

**Done when:** the normalizer's output type is the component props type with no casts.

---

## Step 6 — Replace fake progress with the real state machine

This is the core of the swap. Data sources are easy to replace; fake progress is not.

**Do:** Rewrite the hook so every UI state is driven by a real event: a request starting, a response arriving, a status value, a poll result, a user action.

**How:**

1. List the UI states the screen already shows (from Step 2's timers).
2. For each one, name the real event that enters it and the real event that leaves it. Use the status table from Step 1.
   - **Request runs inside the call:** "in progress" = the request is pending; the response's status decides the next state.
   - **Request runs in the background:** "in progress" = polling; stop polling on a terminal status, on unmount, and on a new run.
3. A UI state that has no real event behind it is either merged with a neighbor or shown as an indeterminate "working" state. Do not keep a timer that pretends to know progress the backend does not report.
4. Remove flags that the response now carries (e.g. a `hasQuestions` prop when `status` says it).
5. Guard against overlap: lock the actions that start or continue a run while a request is in flight, and ignore responses that belong to an earlier run (compare a request id or run id before applying).
6. Keep the intro/exit animations, but trigger them from these events, not from fixed delays.

**Output:** A transition table and the rewritten hook:

| From | Event | To | UI shows |
| --- | --- | --- | --- |

**Done when:** no `setTimeout` remains that stands in for backend progress, and every status from Step 1 maps to exactly one UI state.

---

## Step 7 — Add the states the dummy never had

**Do:** For each point in the response space that the dummy never produced, decide what the screen shows and what the user can do.

**How:** Go through this list in order. Keep only rows that are real for this endpoint (from Step 1); drop the rest with a reason.

| Situation | Screen shows | User can do |
| --- | --- | --- |
| Request pending, short | The existing in-progress state | Nothing new (actions locked) |
| Request pending, long (past a threshold) | A "still working" line, so it doesn't look frozen | Wait |
| Timeout / network failure | A clear failure message; keep what the user typed | Try again |
| Input rejected (4xx validation) | The backend's message at the input that caused it | Edit and resubmit |
| Run failed, retryable | Failure message | **Retry** (calls the retry endpoint) |
| Run failed, not retryable | Failure message | **Start again** (new run) |
| Conflict (409) | Re-read the run's current status and show that | Whatever that status allows |
| Not found (404) | Reset to the starting screen | Start a new run |
| Not signed in (401 after refresh fails) | Whatever the app does for an expired session | Sign in |
| Success with empty lists | An empty state for that section (one line, not a blank card) | Continue |
| Success with partial fields | The section with the missing parts marked as unknown | Continue |
| Page refresh mid-run | Restore from the saved run id (e.g. `sessionStorage`) via the status endpoint | Continue where it was |

Rules:

- Always say what happened **and** what the user can do next. A message with no action is a dead end.
- Never discard what the user typed on a failure.
- Use the backend's `retryable` flag (or equivalent) to choose between Retry and Start again; don't guess from the status code.

**Output:** The table above, filled for this screen, and the components or copy each row needs.

**Done when:** every error code and status from Step 1 has a row, and each row has a user action.

---

## Step 8 — Map open-ended domain values to presentation

**Do:** Where the UI picks an icon, color, label or layout from a backend value (a taxonomy node, a category type, an enum), build an explicit map for it.

**How:**

- Take the full value set from the backend's source of truth (the taxonomy file or enum), not from the dummy data. Dummy data covers a handful of values; live data covers all of them.
- Map by **group** first (one icon/color per group of values), then override individual values that need their own. Do not hand-write hundreds of entries.
- Always have a fallback for values outside the map, and use it for free text (user-worded names) that can never be in the set.
- Replace regex or keyword guessing that was tuned to the dummy text, unless it is only the fallback for free text.

**Output:** The map, its fallback, and a test that every value in the backend's set resolves to a style.

**Done when:** the coverage test passes against the backend's full value set.

---

## Step 9 — Swap and verify, one screen state at a time

**Do:** Replace the dummy source with service → normalizer → hook, then check each state on the running app.

**How:**

1. Swap one data source at a time. After each, run the app against the real backend and check the screen renders the same as with dummy data.
2. Then walk each row of Step 6's transition table and Step 7's situation table on the running app. Force the failure rows (stop the backend, send short input, call retry twice, refresh mid-run).
3. Watch the console and network panel: no unhandled errors, no duplicate requests, no request firing after unmount.

**Output:** A short checklist with each state marked verified, or the reason it could not be forced.

**Done when:** every row is verified or explicitly listed as not forced.

---

## Step 10 — Tests, then move the dummy data

**Do:** Turn the dummy data into mocked API responses and test the screen against them.

**How:**

- Move the dummy objects into test fixtures as **API response bodies** (with `status` and the other top-level fields), not as component props. Keep them as the "happy" fixtures.
- Add fixtures for the other points in the response space: each status, empty lists, missing optional fields, unknown enum value, each error code.
- Mock at the network boundary (the fetch call), not the hook or the service, so the whole chain is tested.
- Pick test cases with the state-testing skill (`state_testing.md`): transitions, interruption/recovery, concurrency, idempotency, persistence across refresh. Assert only on what the user can see and do.
- Remove the dummy imports and default props from the page. Delete nothing that a fixture still uses.

**Output:** Fixtures, tests, and a page with no dummy imports.

**Done when:** the tests cover every row of Steps 6 and 7 that applies, and `grep` finds no dummy import outside tests.

---

## What to hand back

At the end, report in this order:

1. The contract and status tables (Step 1).
2. The gap table with owners (Step 3).
3. The transition table (Step 6) and situation table (Step 7).
4. What was verified on the running app, and what could not be forced (Step 9).
5. Any component that had to change, and why (rule 3).

## What this skill does not do

- It does not redesign the screen. If a live-data state needs new design, record it and hand it to the design workflow.
- It does not change the backend in any way: no endpoint, contract or serialization changes (rule 2). If a gap truly cannot be absorbed on the frontend, stop and report it instead of editing the backend.
- It does not add features the dummy screen did not have, beyond the states in Step 7.
