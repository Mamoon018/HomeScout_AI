# Frontend Mock Mode: as built → dev-only mock data mode

Revision 2. This revision folds in the decisions on D1, F1, F2, F6, F7 and F11. IDs are
kept stable from revision 1.

**Implementation notes.** These were added during the build and refine A4 and F1 below.
- **Coherent dataset.** The existing fixtures held two stories that don't join: R1 and R2
  are a Munich brief, while R3 is an Amsterdam gym and museum chain. The dev mock serves one
  new coherent story, `src/mocks/fixtures/devStory.ts`. It reuses the Munich R1 fixtures,
  adds R2 places for that plan's categories, and adds R3 rows that answer its two questions.
  The contract test checks that the three join into one places-metrics page.
- **Reload.** An ID the in-memory store hasn't seen answers its scenario's end state
  (finished, or failed in `error`) instead of replaying the sequence. Starting or reading a
  child marks its parents finished, so the R3 → R2 → R1 walk and direct `?run=` links always
  resolve.
- **Docker.** The build script now runs `scripts/checkNoMock.mjs`, so the Dockerfile copies
  `scripts/`.

## 1. Confirmation

**Inputs read**
- **Old spec and plan.** There is no spec or plan document for mock mode, because the
  feature does not exist yet. "Implemented" means the frontend as it stands in the repo:
  branch `frontend-demo-ready-changes`, last commit `e6fd083`. The build rules are in
  `skills/react_code_rules.md`, which has now been updated for D1 (see M3).
- **Artifact names.** These come from the repo itself rather than a plan, so every file
  path named here exists today. Files that do not exist yet are marked `(illustrative)`.
- **New spec.** The system-design decisions finalized in this conversation:
  - Dev-only flag `VITE_USE_MOCK_API`, which only takes effect together with
    `import.meta.env.DEV`.
  - A `fetch` interceptor installed from `main.tsx` that answers `/api/*` and
    `/auth/refresh`, and passes all other traffic through.
  - A `?mock=` scenario: `happy` (the default), `running`, `paused`, `error`, `not-found`,
    `empty`, `slow` or `unauthenticated`.
  - Mock run IDs start with `mock_`.
  - A 300 ms default delay.
  - A "MOCK DATA" badge and a console banner.
  - A fixture-contract test through the real normalizers.
  - A production-leak build check.
  - Storage reset when the mode changes.
  - A loud 501 for unhandled `/api` routes.
  - Named failure codes: `mock_unhandled_route`, `mock_unknown_scenario`,
    `mock_fixture_invalid`, `mock_state_stuck`, `mock_leaked_to_prod`, `mock_state_mixed`.

**Decisions added in revision 2**

| Was | Decision | Lands in |
|---|---|---|
| D1 | The fixtures move to `src/mocks/fixtures/`. The rules file is updated: the earlier `test/fixtures/` rule was decided before a second consumer existed. The fake backend (interceptor, routes, scenarios, run store) lives beside the fixtures in `src/mocks/`. The mode switch and storage reset stay in `lib/`. | M3, A1–A8 paths |
| F1 | Each scenario has fixed, pre-built run IDs, one per stage: `mock_<scenario>_r1`, `_r2`, `_r3`. The ID carries its scenario, so it survives `?mock=` being dropped and survives a reload. | A3, A4 |
| F2 | `paused` has a defined meaning on every page: R1 holds at `needs_answers`; R2 and R3 hold at `running`, the same as the `running` scenario, with a `console.info` saying so. | A3 |
| F6 | The mock's poll cap equals R1's `MAX_POLLS` (70) and is not lowered. On R1 the app's own offline notice still wins, so `mock_state_stuck` in practice guards R2 and R3. | A4 |
| F7 | R2's "still going" threshold rises from 12 s to 120 s, in line with R1's 120 s work timeout. `slow` then means up to 120 s on R1 and R2, and up to 4 min on R3. | M4, A5 |
| F11 | Keep the `mock_state_mixed` warning in `lib/apiClient.ts`. | A7 |

**Not in scope**
- The uncommitted sign-up validation work in the working tree. This iteration does not
  touch it.

**Done during this review**
- `skills/react_code_rules.md` was edited. It now has a `mocks/` layer, a
  `test/mock-backend/` folder for its tests, and rule 17 (mock isolation). The Tests
  section no longer holds the fixtures.

**Result:** 8 ADD, 4 MODIFY, 0 REMOVE, 0 DECISION-GATED. D1 was resolved and became M3.

## 2. Current traceflow, change locations

```
npm run dev ──► main.tsx                                                    ◄── M1, A1
├─ createRoot(#root).render(StrictMode ─ AppRoutes, Toaster)                ◄── A6
│    └─ AppRoutes (routes/AppRoutes.tsx)
│         ├─ /auth/login ──► useLogin ──► authApi.login ──► POST /api/auth/login
│         ├─ /auth/signup ──► authApi.signUp ──► Supabase SDK (not /api)
│         ├─ /home ──► HomePage
│         │    ├─ useWelcomeMessage ──► GET /api/user_welcome
│         │    └─ useR1Run ──► r1Api ──► /api/requirement-interpretation/runs
│         ├─ /proximity_info ──► useR2Run ──► r2Api, poll 2 s, URL ?run=
│         │    └─ "still going" notice after SLOW_AFTER_MS = 12 s           ◄── M4
│         └─ /places_metrics ──► useR3Run ──► r3Api, poll 4 s, URL ?run=
├─ tab storage
│    ├─ sessionStorage homescout.r1.runId, homescout.r2.run                 ◄── A7
│    └─ localStorage homescout.auth.user                                    ◄── A7
└─ every /api call ──► lib/apiClient.apiFetch                               ◄── A7
     ├─ 401 token_expired ──► POST /auth/refresh ──► retry once
     ├─ still 401 ──► useUnauthenticatedRedirect ──► /auth/login
     └─ window.fetch ──► Vite proxy ──► backend :8000                       ◄── A2, A3, A4, A5

test/ (Vitest only)
├─ fixtures/ r1*, r2Bodies, r3Bodies (6 files)                              ◄── M3, A8
└─ r1Server, r2Server, r3Server ──► vi.stubGlobal('fetch')

npm run build ──► tsc -b && vite build ──► dist/ ──► Dockerfile ──► nginx   ◄── M2
```

| ID | Class  | Summary                                                                   |
|----|--------|---------------------------------------------------------------------------|
| A1 | ADD    | Mock mode switch: `VITE_USE_MOCK_API` and DEV                             |
| A2 | ADD    | `fetch` interceptor and route table, with a 501 for unknown routes        |
| A3 | ADD    | Scenario selection: `?mock=` at start, then read back from the run ID     |
| A4 | ADD    | Run store: fixed IDs per scenario and stage, a step per read, a poll cap  |
| A5 | ADD    | Delay on purpose: 300 ms by default; `slow` up to 120 s / 120 s / 4 min   |
| A6 | ADD    | Mode indicator: "MOCK DATA" badge and console banner                      |
| A7 | ADD    | Storage reset on mode switch and a `mock_state_mixed` warning             |
| A8 | ADD    | Fixture-contract test through the real normalizers                        |
| M1 | MODIFY | `main.tsx` start-up: install the mock before the first render             |
| M2 | MODIFY | `npm run build` gains a production-leak gate                              |
| M3 | MODIFY | Fixtures move from `test/fixtures/` to `mocks/fixtures/`, rules updated   |
| M4 | MODIFY | R2 "still going" notice: 12 s → 120 s                                     |

## 3. ADD

### A1: Mock mode switch

| Artifact | Change |
|---|---|
| frontend/.env.example | modify: add a commented `VITE_USE_MOCK_API=true` line beside the existing captcha toggle. Developers find the switch there and set it in their own `.env.local`. |
| src/vite-env.d.ts · ImportMetaEnv | modify: declare the optional flag next to `VITE_CAPTCHA_ENABLED`, so reading it is typed. |
| src/lib/mockMode.ts (illustrative) · isMockMode | add: the single place that decides the mode. It is on only when the flag is `"true"` and `import.meta.env.DEV` is true, so no production build can turn it on. It lives in `lib/` (configuration), not `mocks/`, because it also has to run in live mode. |
| vite.config.ts · envPrefix | check only: `VITE_` is already exposed to the client, so no change is needed. |
| test/lib/mockMode.test.ts (illustrative) | add: the four cases of flag (on or off) against DEV (true or false). Only "on and DEV" gives mock mode. |

BEFORE
```
main.tsx
└─ render the app
     └─ every /api call ──► Vite proxy ──► backend :8000
```

AFTER
```
main.tsx
├─ isMockMode()                                           ◄── NEW
│    ├─ VITE_USE_MOCK_API = "true" and DEV ──► mock on    ◄── NEW
│    └─ anything else                      ──► mock off   ◄── NEW
└─ render the app
     └─ every /api call ──► Vite proxy ──► backend :8000
```
The last line is unchanged when mock mode is off.

Behaviour change: a developer turns mock mode on from `.env.local`. With the flag unset, or in any production build, the app behaves exactly as it does today.

### A2: `fetch` interceptor and route table

| Artifact | Change |
|---|---|
| src/mocks/mockFetch.ts (illustrative) · installMockFetch | add: wraps `window.fetch` once. Requests under `/api` and `/auth/refresh` go to the route table. Everything else (Supabase, Turnstile, static assets) goes to the real `fetch` untouched. |
| src/mocks/mockRoutes.ts (illustrative) | add: maps method and path to a handler for every endpoint the app calls: `POST /api/auth/login`, `POST /auth/refresh`, `GET /api/user_welcome`; R1 `POST runs`, `GET runs/:id`, `POST :id/clarification-answers`, `POST :id/retry`; R2 and R3 `POST runs`, `GET :id`, `POST :id/retry`. Each handler returns a real `Response` with the backend's status codes and JSON shapes. |
| unhandled `/api` route (illustrative) | add: answers `501 {code: "mock_unhandled_route"}` and logs a `console.error` naming the method and path. It never falls through to the proxy, so a gap can't silently hit the real backend. |
| src/lib/apiClient.ts · fetchJson | check only: `fetchJson` calls `window.fetch` at call time, so the wrapper is picked up without changes. Refresh-and-retry runs against the mocked `/auth/refresh`. |
| features/*/api/r1Api.ts, r2Api.ts, r3Api.ts | check only: `classify` and the normalizers run unchanged on mocked responses. They are the contract the mock must satisfy. |
| test/mock-backend/mockFetch.test.ts (illustrative) | add: one case per route, a pass-through case for a non-`/api` URL, and the 501 case for an unknown `/api` path. |

BEFORE
```
lib/apiClient.fetchJson
└─ window.fetch(path)
     └─ Vite proxy ──► backend :8000
          ├─ JSON reply   ──► r*Api.classify ──► normalizer
          └─ backend down ──► networkError ──► page notice
```

AFTER
```
lib/apiClient.fetchJson
└─ window.fetch(path)                                                           ◄── CHANGED
     ├─ mock off ──► Vite proxy ──► backend :8000
     └─ mock on  ──► installMockFetch wrapper                                   ◄── NEW
          ├─ not /api, not /auth/refresh ──► real fetch (Supabase, Turnstile)   ◄── NEW
          ├─ known route  ──► handler ──► Response, backend-shaped JSON         ◄── NEW
          │    └─ r*Api.classify and the normalizers run unchanged              ◄── NEW
          └─ unknown /api ──► 501 mock_unhandled_route + console.error          ◄── NEW
               └─ the page shows its normal "unavailable" notice                ◄── NEW
```

Behaviour change: with mock mode on, every backend call is answered in the browser, in the backend's own shapes. No backend, proxy or login is needed. Login isn't needed because the pages only redirect on a 401 and never check for a stored user.

### A3: Scenario selection

| Artifact | Change |
|---|---|
| src/mocks/mockScenario.ts (illustrative) · readScenario | add: reads `?mock=` once at start-up. Known names: `happy` (the default), `running`, `paused`, `error`, `not-found`, `empty`, `slow`, `unauthenticated`. An unknown name falls back to `happy` with a `console.warn` naming `mock_unknown_scenario`. The value only decides which fixed IDs a *start* call hands out (A4). |
| src/mocks/mockScenario.ts (illustrative) · scenarioOf(runId) | add: every read, answer and retry call takes its scenario from the run ID itself (`mock_<scenario>_rN`), not from the URL. `useR2Run` and `useR3Run` replace the query string with `{ run }`, which drops `?mock=`, so the URL can't be relied on after a run starts. |
| scenario-to-page map (illustrative) | add: `paused` holds R1 at `needs_answers`. On R2 and R3, which have no paused state, it holds at `running`, the same as the `running` scenario, with a `console.info` saying so. Every other name means the same thing on every page. |
| `unauthenticated` handlers (illustrative) | add: the run and welcome routes answer `401 token_expired` and `/auth/refresh` fails. The app's real redirect path then runs and the page lands on `/auth/login`. |
| features/r2-proximity/hooks/useR2Run.ts, features/places-metrics/hooks/useR3Run.ts · setParams | check only: not changed. Keeping the scenario in the ID makes this harmless. |
| test/mock-backend/mockScenario.test.ts (illustrative) | add: each known name, the fallback for an unknown name, the default when the parameter is absent, scenario recovery from an ID, and `paused` on each page. |

BEFORE
```
page load
└─ hooks call the API ──► whatever state the live backend happens to be in
```

AFTER
```
page load
├─ readScenario(?mock=)                                                     ◄── NEW
│    ├─ known name   ──► start calls hand out that scenario's fixed IDs     ◄── NEW
│    └─ unknown name ──► happy + warn mock_unknown_scenario                 ◄── NEW
└─ hooks call the API ──► mock answers in the chosen scenario's state       ◄── CHANGED
     ├─ read, answers or retry ──► scenario taken from mock_<scenario>_rN   ◄── NEW
     ├─ paused on R2 / R3 ──► held at running + console.info                ◄── NEW
     └─ unauthenticated ──► 401 ──► refresh fails ──► /auth/login           ◄── NEW
```

Behaviour change: any UI state, including the redirect on a lost session, can be reached on purpose from the URL. The scenario survives the app rewriting the URL and survives a reload.

### A4: Run store with fixed IDs per scenario

| Artifact | Change |
|---|---|
| src/mocks/mockRunIds.ts (illustrative) | add: a fixed table with three IDs per scenario, one per stage: `mock_<scenario>_r1`, `mock_<scenario>_r2`, `mock_<scenario>_r3` (for example `mock_error_r2`). The links between stages are fixed in the same table, so an ID can never point at nothing. |
| src/mocks/mockRunStore.ts (illustrative) | add: an in-memory map from fixed ID to current step and read count. A start call answers with that scenario's fixed ID, which the app saves to `sessionStorage` or `?run=` as usual. Starting again returns the same ID. A reload empties the map, so the run plays its sequence again from the start. |
| progression rules (illustrative) | add: R1 runs `running` ──► `needs_answers` ──► answers sent ──► `running` ──► `finished`. R2 and R3 return 202 `running`, then `finished` after a few reads (about 10–20 s of playback at the app's 2 s and 4 s polls). In `error`, a run goes to `failed` with `retryable`, and Retry takes it ──► `running` ──► `finished`. In `not-found` a read answers 404. In `empty` a run finishes with no places or no questions. |
| run chain (illustrative) | add: R2 starts from the R1 ID the app saved. The R3 result walks R3 ──► R2 ──► R1 through the IDs linked in the table. The same lookup works after a reload, because the IDs are fixed. |
| unknown `mock_` ID (illustrative) | add: an ID with the `mock_` prefix that isn't in the table (a typo, or one left over from an older table) answers 404 and logs `mock_unknown_scenario`. The page then shows its normal "not found" state. |
| poll cap (illustrative) | add: after 70 reads (the same value as R1's `MAX_POLLS`), a run answers `failed` and logs `mock_state_stuck`. R1 stops polling at 70 and shows its own offline notice first. R2 and R3 have no cap of their own, so this is their guard. |
| src/mocks/fixtures/ (M3) | read: response bodies come from the fixtures. The fixtures keep their own UUID `RUN_ID`s, which the tests rely on. The store sends a copy with the run ID and its parent ID (`r1_run_id`, `r2_run_id`) replaced by the scenario's fixed IDs. The normalizers accept any string as an ID, so no other change is needed. |
| features/r1-interpretation/hooks/useR1Run.ts, useR2Run.ts, useR3Run.ts | check only: polling, backoff and the phase transitions run unchanged against the store. (`useR2Run` changes only for M4.) |
| test/mock-backend/mockRunStore.test.ts (illustrative) | add: each scenario's sequence of states per feature, the chain lookup before and after a simulated reload, the unknown-ID 404, and the poll cap. |

BEFORE
```
useR2Run / useR3Run
├─ start ──► backend creates the run ──► 202 running
└─ poll every 2 s / 4 s ──► backend run row
     ├─ running  ──► poll again
     ├─ finished ──► show the result
     └─ failed   ──► Retry or Start again
```

AFTER
```
useR2Run / useR3Run
├─ start ──► fixed ID mock_<scenario>_r2 / _r3 ──► 202 running           ◄── CHANGED
└─ poll every 2 s / 4 s ──► mock store advances that ID one step         ◄── CHANGED
     ├─ running           ──► poll again
     ├─ finished after a few reads ──► fixture body with fixed IDs       ◄── CHANGED
     ├─ failed (error)    ──► Retry ──► running ──► finished             ◄── CHANGED
     ├─ after 70 reads    ──► failed + mock_state_stuck                  ◄── NEW
     └─ unknown mock_ ID  ──► 404 + mock_unknown_scenario                ◄── NEW
useR1Run: start ──► running ──► needs_answers ──► answers ──► finished   ◄── NEW
useR3Run finished ──► R3 ──► R2 ──► R1 through the linked fixed IDs      ◄── NEW
reload ──► same fixed ID ──► recognised ──► sequence starts again        ◄── NEW
```

Behaviour change: pages show real transitions over about 10–20 s instead of a frozen state. Every mock ID always resolves, including after a reload, which simply replays the sequence.

### A5: Delay on purpose

| Artifact | Change |
|---|---|
| src/mocks/mockFetch.ts (illustrative) · reply delay | add: every mocked reply waits 300 ms by default. This keeps skeletons, waiting lines and transitions visible instead of skipped. |
| `slow` scenario (illustrative) | add: the reply waits until just past each page's own slow point. R1 up to its 120 s work timeout, R2 up to its "still going" notice at 120 s (after M4), and R3 up to its notice at 4 min. Those notices, and the R1 timeout, can then be checked. |
| src/lib/apiClient.ts · API_TIMEOUT_MS (15 s); r1Api.ts · R1_WORK_TIMEOUT_MS (120 s); useR3Run.ts · SLOW_AFTER_MS (4 min) | check only: read so the delays line up with them. Not changed. |
| src/features/r2-proximity/hooks/useR2Run.ts · SLOW_AFTER_MS | read: the value after M4 (120 s). |

BEFORE
```
window.fetch ──► backend
└─ reply time = real backend time (R1 LLM steps: tens of seconds)
```

AFTER
```
window.fetch ──► mock handler                                         ◄── CHANGED
├─ wait 300 ms by default                                             ◄── NEW
├─ slow on R1 ──► wait up to 120 s (work timeout)                     ◄── NEW
├─ slow on R2 ──► wait past 120 s ──► "still going" notice            ◄── NEW
├─ slow on R3 ──► wait past 4 min ──► "still going" notice            ◄── NEW
└─ reply ──► skeletons, waiting panels and slow notices are visible   ◄── NEW
```

Behaviour change: mocked pages behave with realistic, predictable timing, and each page's slow path can be reached on purpose.

### A6: Mode indicator

| Artifact | Change |
|---|---|
| src/components/mock-badge.tsx (illustrative) · MockBadge | add: a fixed "MOCK DATA · `<scenario>`" marker, shown on every route including login. You can always see which mode you're in. It is UI, so it lives in `components/`, not `mocks/`, and only renders when `isMockMode()` is true. |
| src/main.tsx | modify: mounts `MockBadge` beside `Toaster`, only in mock mode. There is no shared layout, so mounting it here leaves every page file untouched. |
| src/mocks/mockFetch.ts (illustrative) · start-up banner | add: one `console.info` at install naming the mode and the scenario. |
| src/assets/design/theme-olive.css, linear-tokens.css | check only: the badge uses existing tokens; no new colours. |

BEFORE
```
main.tsx render
├─ AppRoutes
└─ Toaster
```

AFTER
```
main.tsx render
├─ AppRoutes
├─ Toaster
├─ MockBadge "MOCK DATA · <scenario>" (mock mode only)   ◄── NEW
└─ console banner: mock mode on, scenario <name>         ◄── NEW
```

Behaviour change: mock mode is impossible to miss, on screen or in the console.

### A7: Storage reset on mode switch and mixed-state warning

| Artifact | Change |
|---|---|
| src/lib/mockMode.ts (illustrative) · resetOnModeChange | add: stores the last mode (mock or live) in `localStorage`. When this load's mode differs, it clears the stored run and user before the first render, so IDs from one mode never reach the other. It runs in both modes, because the switch from mock back to live is the one that needs cleaning. So it lives in `lib/` and ships in the production bundle. In production the stored mode is always live, so it never clears anything there. |
| features/r1-interpretation/utils/runStorage.ts · clearRunId; features/r2-proximity/utils/runStorage.ts · clearR2Run; features/auth/utils/authUserStore.ts · clearAuthUser | check only: the reset calls these existing functions instead of touching the raw keys. Their code is not changed. |
| src/lib/apiClient.ts · apiFetch | modify (kept by decision F11): when mock mode is off and a request path contains a `mock_` ID, logs `console.warn` with `mock_state_mixed`. This covers a bookmarked `?run=mock_…` URL that the storage reset can't reach. |
| test/lib/apiClient.refresh.test.ts | check only: the refresh behaviour stays the same. The warning and the reset get their own cases in `test/lib/mockMode.test.ts`. |

BEFORE
```
page load
├─ useR1Run reads homescout.r1.runId ──► GET runs/<id>
└─ useR2Run reads homescout.r2.run   ──► GET runs/<id>
     └─ an ID from another mode ──► 404 ──► "not found" with no hint why
```

AFTER
```
page load
├─ resetOnModeChange: mode changed since the last load?                 ◄── NEW
│    ├─ yes ──► clearRunId, clearR2Run, clearAuthUser                   ◄── NEW
│    └─ no  ──► storage kept
├─ useR1Run reads homescout.r1.runId ──► GET runs/<id>
├─ useR2Run reads homescout.r2.run   ──► GET runs/<id>
└─ live mode + mock_ ID in the path ──► console.warn mock_state_mixed   ◄── NEW
```

Behaviour change: switching the flag never sends a stored mock ID to the real backend, and a stale mock URL explains its own 404.

### A8: Fixture-contract test

| Artifact | Change |
|---|---|
| test/mock-backend/mockFixtures.contract.test.ts (illustrative) | add: runs every fixture body in `src/mocks/fixtures/` through its real normalizer: `normalizeRun`, `normalizeR2Run`, `normalizeR3Run`, and `welcomeMessageFromResponse` for the welcome body. It also runs them as the mock stamps them with fixed IDs. It fails with `mock_fixture_invalid` and the fixture's name if any returns null. |
| features/r1-interpretation/utils/normalizeRun.ts, features/r2-proximity/utils/normalizeR2Run.ts, features/places-metrics/utils/normalizeR3Run.ts | check only: used as they are, because they are the frontend's statement of the backend contract. |
| test/r1-interpretation/normalizeRun.test.ts | check only: it already covers some R1 bodies. The new test covers every fixture in one place and doesn't replace it. |

BEFORE
```
npm run test
├─ page tests use the fixtures through r1Server, r2Server, r3Server
└─ a fixture that no longer matches the backend ──► noticed only if a page test breaks
```

AFTER
```
npm run test
├─ page tests use the fixtures through r1Server, r2Server, r3Server
└─ contract test: every fixture, as stored and as stamped ──► normalizer   ◄── NEW
     ├─ parses       ──► pass                                              ◄── NEW
     └─ returns null ──► fail mock_fixture_invalid <fixture>               ◄── NEW
```

Behaviour change: drift between the fixtures and the frontend's view of the backend contract fails the test run instead of showing up later as a misleading mock page.

## 4. MODIFY

### M1: `main.tsx` start-up order

| Artifact | Change |
|---|---|
| src/main.tsx | modify: before `createRoot().render`, run `resetOnModeChange` (A7) in both modes. In mock mode, load `src/mocks/` through a DEV-only dynamic import, read the scenario (A3) and install the interceptor (A2), then render. This dynamic import is the only way into `mocks/` (rule 17), so live builds don't contain the mock code. |
| test/pages/*.test.tsx | check only: page tests render pages directly, not `main.tsx`, so they are unaffected. |

BEFORE
```
main.tsx
└─ createRoot(#root).render(StrictMode ─ AppRoutes, Toaster)
```

AFTER
```
main.tsx
├─ resetOnModeChange()                                                     ◄── NEW
├─ isMockMode()?                                                           ◄── NEW
│    ├─ yes ──► import @/mocks (DEV only) ──► scenario ──► install fetch   ◄── NEW
│    └─ no  ──► nothing loaded                                             ◄── NEW
└─ createRoot(#root).render(StrictMode ─ AppRoutes, Toaster, MockBadge?)   ◄── CHANGED
```

Behaviour change: in mock mode, rendering waits until the interceptor is in place, so the very first API call is already mocked. Live start-up only gains the storage check.

### M2: Production-leak gate on `npm run build`

| Artifact | Change |
|---|---|
| frontend/package.json · scripts.build | modify: after `vite build`, run the leak check. The build then fails if mock code reached `dist/`. |
| frontend/scripts/checkNoMock (illustrative) | add: scans `dist/` for the mock marker string. If found, it stops with `mock_leaked_to_prod` and the file name. |
| src/mocks/ marker constant (illustrative) | add: a unique string inside the mock code that the check looks for. It must differ from the `mock_` prefix and the `mock_state_mixed` text, which do legitimately ship in `lib/`. |
| frontend/Dockerfile | check only: the image already runs `npm run build`, so a leak also fails the Docker build. `COPY src ./src` copies `src/mocks/` into the builder stage, which is harmless because only `dist/` reaches nginx. |

BEFORE
```
npm run build
├─ tsc -b
└─ vite build ──► dist/ ──► Dockerfile copies it into nginx
```

AFTER
```
npm run build
├─ tsc -b
├─ vite build ──► dist/
└─ leak check: is the marker in dist/?               ◄── NEW
     ├─ no  ──► Dockerfile copies dist/ into nginx   ◄── NEW
     └─ yes ──► build fails, mock_leaked_to_prod     ◄── NEW
```

Behaviour change: a production build or Docker image can no longer ship mock code by accident.

### M3: Fixtures move to `src/mocks/fixtures/`

This was D1. The decision was to move them and update the rules, because the earlier
`test/fixtures/` rule was made when tests were the fixtures' only consumer.

| Artifact | Change |
|---|---|
| src/test/fixtures/ r1Bodies, r1Plan, r1Extraction, r1Questions, r2Bodies, r3Bodies ──► src/mocks/fixtures/ | modify: the same six files move, with their contents unchanged apart from their cross-imports, which now point to `@/mocks/fixtures/…`. They become the one copy shared by the tests and the dev mock. |
| test/pages/HomePage.run.test.tsx, ProximityPage.run.test.tsx, PlacesMetricsPage.run.test.tsx; test/r1-interpretation/normalizeRun.test.ts, r1Api.test.ts | modify: the import paths change from `@/test/fixtures/…` to `@/mocks/fixtures/…`. Nothing else about the tests changes. |
| test/r1Server.ts, r2Server.ts, r3Server.ts | check only: they don't import fixtures and stay in `test/`. |
| test/mocks/turnstile.tsx | check only: it stays where it is. `test/mocks/` keeps its meaning (mocked third-party modules), and the rules now say it is not the top-level `mocks/`. |
| skills/react_code_rules.md | modify (done in this review): adds the `mocks/` layer (fixtures plus the dev mock that serves them, loaded only through DEV mock mode), removes the fixtures from the Tests definition, adds `test/mock-backend/` for its tests, and adds rule 17 (mock isolation). |

BEFORE
```
test/fixtures/ (6 files)
├─ read by 5 test files
└─ the fixtures' own cross-imports @/test/fixtures/*
```

AFTER
```
src/mocks/fixtures/ (same 6 files)                                      ◄── CHANGED
├─ read by 5 test files through @/mocks/fixtures/*                      ◄── CHANGED
├─ the fixtures' cross-imports point to @/mocks/fixtures/*              ◄── CHANGED
├─ read by the dev mock (src/mocks/mockRunStore)                        ◄── NEW
└─ test/fixtures/ no longer exists                                      ◄── GONE
skills/react_code_rules.md: mocks/ layer, test/mock-backend/, rule 17   ◄── CHANGED
```

Behaviour change: none at run time. The tests and the dev mock read one copy of the backend's response shapes.

### M4: R2 "still going" notice, 12 s → 120 s

| Artifact | Change |
|---|---|
| src/features/r2-proximity/hooks/useR2Run.ts · SLOW_AFTER_MS | modify: 12 s becomes 120 s. The waiting line on `/proximity_info` now says the run is still going after two minutes instead of twelve seconds, in line with R1's 120 s work timeout. This changes live behaviour, not just mock mode. |
| src/assets/design/R2_frontend_ui_spec.md · Loading (line 102) | modify: the spec says "after 12 seconds (R1's slow wait)". It must say 120 seconds, or the spec and the code disagree. |
| test/pages/ProximityPage.run.test.tsx | check only: no test reads `SLOW_AFTER_MS` or a 12 s literal today. Confirm when implementing and add a case if the notice is covered by a timer test. |

BEFORE
```
useR2Run
├─ start ──► running ──► poll every 2 s
└─ still running after 12 s ──► waiting line says it is still going
```

AFTER
```
useR2Run
├─ start ──► running ──► poll every 2 s
└─ still running after 120 s ──► waiting line says it is still going   ◄── CHANGED
```

Behaviour change: on live and mock runs alike, R2's "still going" line appears after 120 s instead of 12 s.

## 5. REMOVE

None. `test/fixtures/` disappears only as part of M3's move. Its contents are kept.

## 6. DECISION-GATED

None. D1 was resolved: the fixtures move (M3).

## 7. Unchanged

- **Pages and routing:** the pages (`HomePage`, `ProximityPage`, `PlacesMetricsPage`,
  `LoginPage`, `SignupPage`) and `AppRoutes`.
- **Feature code:** the run hooks (`useR1Run`, `useR3Run`, and `useR2Run` apart from
  M4), the API modules (`r1Api`, `r2Api`, `r3Api`, `authApi`), and the normalizers.
- **Auth:** `useUnauthenticatedRedirect`; the refresh-and-retry logic in `apiClient`
  (only the A7 warning is added); Supabase sign-up and Turnstile captcha.
- **Config and tests:** the Vite proxy config (unused in mock mode, still there for live
  mode); the test fake servers (`r1Server`, `r2Server`, `r3Server`); `test/mocks/`; every
  existing test's behaviour (M3 changes only import paths).
- **Deployment:** Docker, nginx and the production runtime.

## 8. Component traceflow after all points

```
npm run dev ──► main.tsx
├─ resetOnModeChange: clearRunId, clearR2Run, clearAuthUser if mode changed   ◄── A7, M1
├─ isMockMode(): VITE_USE_MOCK_API and DEV                                    ◄── A1, M1
├─ mock on ──► import @/mocks (DEV only)                                      ◄── M1
│    ├─ readScenario(?mock=) ──► which fixed IDs start calls hand out         ◄── A3
│    ├─ installMockFetch                                                      ◄── A2
│    └─ console banner                                                        ◄── A6
├─ render AppRoutes, Toaster, MockBadge (mock mode only)                      ◄── M1, A6
│    └─ /proximity_info: "still going" after 120 s                            ◄── M4
└─ every /api call ──► lib/apiClient.apiFetch ──► window.fetch
     ├─ mock off ──► Vite proxy ──► backend :8000
     │    └─ mock_ ID in the path ──► warn mock_state_mixed                   ◄── A7
     └─ mock on  ──► route table                                              ◄── A2
          ├─ wait 300 ms; slow: 120 s R1, 120 s R2, 4 min R3                  ◄── A5
          ├─ scenario from the ID mock_<scenario>_rN                          ◄── A3
          ├─ run store: fixed IDs, one step per read, chain R3 ► R2 ► R1      ◄── A4
          ├─ bodies from src/mocks/fixtures/, stamped with fixed IDs          ◄── A4, M3
          ├─ unauthenticated ──► 401 ──► refresh fails ──► /auth/login        ◄── A3
          ├─ after 70 reads ──► failed, mock_state_stuck                      ◄── A4
          ├─ unknown mock_ ID ──► 404, mock_unknown_scenario                  ◄── A4
          └─ unknown /api route ──► 501 mock_unhandled_route                  ◄── A2
npm run test  ──► contract test on every fixture in src/mocks/fixtures/       ◄── A8, M3
npm run build ──► vite build ──► leak check ──► dist/ ──► Docker              ◄── M2
```

## 9. Flags

| #   | Status | Flag |
|-----|--------|------|
| D1  | Resolved | The fixtures move to `src/mocks/fixtures/` and the rules are updated (M3). The rules edit is already made; the file move is not. |
| F1  | Resolved | The scenario lives in fixed IDs (`mock_<scenario>_rN`), so it survives `setParams({ run })` dropping `?mock=` and survives a reload (A3, A4). |
| F2  | Resolved | `paused`: R1 holds at `needs_answers`; R2 and R3 hold at `running` with a `console.info` (A3). |
| F3  | Open | Sign-up calls the Supabase SDK directly, not `/api`, so it passes through the mock to real Supabase. That matches "everything else passes through", but the sign-up page is not mocked. |
| F4  | Open | The repo has no CI (`.github/` is absent). The leak gate (M2) only runs through `npm run build`, locally and in Docker. It isn't checked on pull requests. |
| F5  | Note | Nothing outside `authUserStore` reads `homescout.auth.user` today; only `useLogin` writes it. Clearing it on a mode switch is harmless. |
| F6  | Resolved | The mock's poll cap stays at 70, the same as R1's `MAX_POLLS`. On R1 the app's own offline notice shows first, so `mock_state_stuck` is in practice the guard for R2 and R3 (A4). |
| F7  | Resolved | R2's "still going" threshold goes to 120 s (M4). `slow` waits up to 120 s on R1 and R2 and up to 4 min on R3 (A5). M4 changes live behaviour and the R2 spec, not only mock mode. |
| F8  | Open | `search-progress` still holds dummy UI (`map-preview.tsx`, `result-preview.tsx`, `useSearchRun.ts`) that no page imports. It's dead code outside this iteration, worth a separate cleanup. |
| F9  | Note | R1 does its work inside the request (start, answers and retry use a 120 s timeout, and the run can come back already finished or `needs_answers`). R2 and R3 answer 202 and are polled. The run store models both shapes. |
| F10 | Note | Calls answered by the interceptor do not appear in the browser's Network tab. This trade-off was accepted when MSW was rejected. |
| F11 | Resolved | The `mock_state_mixed` warning stays in `lib/apiClient.ts` (A7). Together with `resetOnModeChange` in `lib/mockMode.ts`, these are the only mock-aware pieces that ship in production. Neither does anything there. |
| F12 | New | The fixtures keep their UUID run IDs because the tests assert on them. The dev mock stamps the fixed `mock_` IDs onto a copy. The normalizers accept any string ID, so this is safe. The contract test (A8) checks both forms. |
| F13 | New | Choosing the same scenario again returns the same fixed IDs, so "Start again" replays the same run. That's fine for UI work, but two tabs on one scenario share the same IDs. Their run state is still separate, because each tab has its own in-memory store. |
| F14 | New | A second copy of the rules file exists at `.claude/worktrees/deep-search-mechanism-5-plan-7d5d3d/skills/react_code_rules.md`, in another worktree. It was not updated. |
