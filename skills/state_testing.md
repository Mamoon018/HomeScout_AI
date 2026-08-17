
# Guideline: Dimension Selection Before Test Writing

Before writing any tests using the State Testing Dimensions reference, follow this sequence. Do not skip to the dimension table first.

**Step 1 — Understand the feature, not the checklist.**
Read the feature's actual implementation and intended behavior end to end: what states exist, what triggers each state change, what the user is meant to experience at each point, and what happens after the journey completes (success, failure, or abandonment).

**Step 2 — Map the real user journeys.**
List the distinct paths a user (or the system) can take through this feature — happy path, retry path, failure path, interruption path, repeat-use path. Base this on what the feature actually does, not on assumptions borrowed from other features.

**Step 3 — Select only the dimensions that map to real behavior in this feature.**
For each of the 18 dimensions, ask: *does this feature exhibit behavior that this dimension is designed to catch?* Only include a dimension if you can point to a concrete state, transition, or rule in the feature that it applies to. If a dimension has no real counterpart in the feature (e.g., no derived state exists, or no optimistic UI update happens), discard it — do not force-fit a test to it.

**Step 4 — Justify each selected dimension before writing its test.**
For every dimension you keep, write one sentence stating which specific behavior, state, or transition in this feature it is testing. If you cannot articulate that sentence concretely, the dimension is not relevant here and should be dropped.

Add this as an explicit step in your guideline, inserted between current Step 4 and Step 5:

**Step 4a — Prove each dimension is distinct, not just justified.**
For every dimension you're about to keep, ask: *what specific failure would this dimension catch that no other dimension already in my selected list would catch?* Write that failure explicitly.

- If two or more selected dimensions would be caught by the exact same test assertion (e.g., "submit button remains disabled"), they are not distinct — keep only the one whose framing most precisely names the failure mode, and drop the rest.
- A dimension justified only by restating the feature's general rule (e.g., "submit is disabled when no token exists") in different words is not a new dimension — it is the same test relabeled. Only keep it if it points to a *different* trigger, a *different* moment, or a *different* failure than the dimensions already selected.
- Before finalizing the list, produce a short "distinctness check": for each pair of selected dimensions that seem related.

    **Explicit rule for step 4a:** A dimension earns its place only by describing a failure mode no other selected dimension already covers. The number of dimensions justified is not evidence of thoroughness — evidence of thoroughness is that removing any one dimension from the list would leave a real gap in coverage.

**Step 5 — Write tests only for the justified dimensions.**
Do not produce a test for all 18 dimensions by default. Coverage should be judged by whether every real behavior in the feature is tested, not by how many dimensions from the list were used.

**Explicit rule:** Treat the dimension table as a lens for spotting behaviors you might otherwise miss — not as a mandatory checklist to exhaust. A short, targeted test suite built from 5 well-justified dimensions is correct; a test suite covering all 18 dimensions generically, without tying each to actual feature behavior, is incorrect regardless of its size.

# State Testing Dimensions — Quick Reference

| # | Dimension | Tests | Apply When | Key Checks |
|---|-----------|-------|------------|------------|
| 1 | **Transition** | Whether state moves to the next state only via permitted events, not skipped/reversed/invalid paths. | Feature has distinct stages (loading, success, failure, retry, expiry) where order affects what the user can do. | valid transition, invalid transition, skipped state, unauthorized backward transition, user/API/system-triggered transition, resulting UI/side effects |
| 2 | **Reachability** | Whether every intended state can actually be entered under its real conditions, and forbidden states cannot be entered at all. | States like expired, cancelled, timed-out, or recovered depend on specific/rare conditions. | normal route in, exceptional route in, missing route to required state, unreachable state, forbidden state, real-user vs. externally-triggered reachability |
| 3 | **Initialization** | Whether the starting state matches the user's actual entry conditions (data, permissions, URL, prior context). | Multiple entry points, existing server data, saved drafts, new vs. returning users. | new entry, returning entry, existing/missing/invalid data, different entry points/permissions, URL-driven init, unintended init side effects |
| 4 | **Persistence** | What state survives refresh, navigation, or remount vs. what gets discarded. | Drafts, multi-step progress, carts, selections, filters, or other retained work; also transient state that shouldn't survive. | refresh, route change, remount, leave-and-return, partial/persisted progress, stale or invalid persisted state, sensitive state retention |
| 5 | **Invariants** | The conditions that must always hold true while in a given state. | A state imposes rules (e.g., `loading` requires an active op and blocks duplicate submits). | required data present, prohibited data absent, required action enabled, prohibited action blocked, contradictory combinations, invariant holds for full state duration |
| 6 | **Consistency** | Whether multiple representations of the same condition (local, server, cache, URL, flags) stay in sync. | Same business condition tracked in more than one place (e.g., `status` + `isSaved`). | all representations agree, independent updates, stale/contradictory values, async sync, delayed update |
| 7 | **UI correspondence** | Whether visible/accessible UI accurately reflects the current state. | States that change visible content or interactivity (loading, error, empty, disabled, expanded). | correct content/control/indicator/message, stale or missing UI, contradictory UI, accessibility state, transition rendering |
| 8 | **Action availability** | Whether each state enables/disables/hides exactly the actions the feature permits. | Actions change by state (e.g., submit disabled while saving; retry enabled after failure). | allowed vs. prohibited action, disabled/hidden control, programmatic or rapid invocation, action before/during/after transition |
| 9 | **Timing** | Whether state changes at the correct moment relative to actions, async responses, timers, and expiry. | Debounce, throttle, timeout, expiry, polling, animation, or other async-dependent behavior. | immediate vs. delayed transition, timeout/expiry/debounce boundary, slow/fast response, premature or missing transition |
| 10 | **Concurrency** | Which state wins when multiple actions or async operations overlap or resolve out of order. | Search, autosave, uploads, submissions, repeated clicks, or overlapping async work. | overlapping ops, rapid actions, out-of-order responses, stale response, latest-intent-wins, cancellation, duplicate request |
| 11 | **Interruption/recovery** | Whether an interrupted journey (failure, cancellation, nav-away, network loss) reaches a defined recovery state instead of getting stuck. | Long-running ops, multi-step workflows, or journeys users can abandon mid-way. | interruption during idle/loading, network failure, cancellation, nav-away, retry, resume, restart, stuck state, preserved partial progress |
| 12 | **Rollback** | Whether an optimistic state correctly reverts when the confirming operation fails. | UI updates before server confirmation (likes, saves, toggles, edits, deletes). | previous state, optimistic state, success confirmation, server rejection, rollback, preserved input, restored UI/derived state, retry after rollback |
| 13 | **Idempotency** | Whether repeating the same action produces the intended effect, not unintended duplicates. | Submit, save, payment, init, mutation, or toggle actions triggerable more than once. | single vs. double vs. rapid invocation, repeat after completion, duplicate request/state/side effect, safe repetition |
| 14 | **Lifecycle/reset** | Whether state is correctly created, retained, or discarded across open/close/remount/context changes. | Modals, tabs, routes, reused components, or entity/context switches where old state may become invalid. | open/close/reopen, mount/unmount/remount, route or entity change, temporary reset vs. meaningful retention, stale-state leakage |
| 15 | **Boundary** | Whether state stays correct as it crosses component/server/URL/store/cache boundaries. | One condition represented across multiple systems (URL filters, server status, form state, global auth) that can update independently. | component↔server update, URL↔state update, store/cache sync, stale data, conflicting source, representation transformation, delayed sync |
| 16 | **Derivation** | Whether computed state (`isValid`, `canSubmit`, `isDirty`, counts) always reflects its current source values. | A value is calculated from other state and gates UI or actions. | source change → derived update, valid↔invalid transition, multiple dependencies, stale derived value, missing dependency update |
| 17 | **History** | Whether earlier events in the journey correctly affect current behavior when current state alone is insufficient. | Retries, undo/redo, prior failures/successes, or flags like `hasRetried` that the feature explicitly depends on. | first attempt vs. retry, prior failure/success, undo/redo, same current state with different history, history reset or leakage |
| 18 | **Cross-journey** | Whether the same state behaves correctly across different legitimate journeys or entry points. | A reusable component/state is reached via new-user, returning-user, retry, edit, or recovery flows with different expectations. | new-user vs. returning-user, retry/edit/cancellation/recovery journeys, same state with different context, journey-specific expected outcome |


## Guideline: Test the Experience, Not the Implementation

All tests must verify what a user can actually perceive and do on screen — never how the feature is built internally. The goal of this tests is to go through the same jpurney a real user goes through: look at what's rendered, interact with it the way a mouse/keyboard/screen-reader would, and check what changed in that same observable layer afterward.

**1. Query only by what a user can perceive.**
Use accessible, role-based queries as the default and only method of locating elements — `getByRole`, `getByLabelText`, `getByText`, `getByPlaceholderText`, `getByAltText`. Never query by CSS class names, component names, internal `data-testid` as a first choice, DOM structure, or any selector a user cannot see or hear. If an element cannot be found via an accessible query, that is itself a defect to flag — not a reason to fall back to an implementation-based selector.

**2. Never assert on internal state, props, or function calls.**
Do not inspect component state variables, hook return values, Zustand/Redux store contents, or whether an internal function (e.g., `resetCaptcha`, `setCaptchaToken`) was called. Assert only on what changed in the rendered, accessible output as a result of that internal change — the disabled attribute a screen reader would announce, the text now visible, the element that appeared or disappeared.

**3. Simulate interactions the way a real user performs them.**
Use `userEvent` (not `fireEvent`) to click, type, and tab through the form, since it mirrors real browser event sequences (focus, pointer, keyboard) rather than firing a single synthetic event. Do not call component methods or trigger callbacks directly — every test action must be something a user could physically do: click a button, type into a field, wait for a page to load.

**4. Assert on user-facing consequences, not the mechanism that produced them.**
For every behavior, ask "what would the user see, hear, or be able to do differently?" and assert exactly that — e.g., assert the Submit button has `aria-disabled`/is unclickable, not that a boolean flag is `false`; assert "Verification Completed" text with its role/status is visible, not that a state enum equals `'success'`.

**5. Respect async timing the way a user experiences it.**
Use `findBy*` queries and `waitFor` to wait for UI to update after async operations (captcha verification, API calls), rather than resolving promises manually or advancing internal timers to infer state changes. The test should wait the way a user would wait, and assert only once the UI has actually changed.
