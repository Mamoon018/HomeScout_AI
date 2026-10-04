
---
name: drift-aware-implementer
description: Use when the user wants backend implementation code written or extended. Pushes the agent past happy-path code: it surfaces the assumptions each operation makes, scans a fixed set of drift categories, and handles only the ones that can genuinely be violated and would matter — at the right boundary, with a deliberate response for each. Opinionated about handling drift AND about which drift is worth handling, so the output is robust without being paranoid.
---

# Drift-Aware Implementer

Happy-path code is the implementation of the one story where every assumption holds. It is not wrong — it is **incomplete**. This skill makes the agent write the rest of the story: the drifts that reality will supply at the boundaries. The failure to avoid is twofold — shipping happy-path-only code, *and* over-correcting into paranoid code that defends against everything. Both are failures.

The discipline in one line:

> **Scan wide to see every assumption; handle narrow — only the drifts that can plausibly be violated and would matter — at the boundary where they enter, with a deliberate response, never swallowed.**

---

## What this skill produces

**The deliverable of this skill is a per-method drift breakdown in the implementation plan — one short entry per method — not drift-handling code written out in the plan.**

The agent using this skill does the drift thinking *on paper first*: for each method it will implement, it writes a small entry that records which drifts are live, where each is handled, how it responds, and — just as importantly — what it deliberately left out. These entries are cheap, reviewable before any code exists, and are the implementation-side mirror of a test plan: a review gate.

Everything below (the two faculties, the seven-category scan, the boundary and response rules) is **the method the agent uses to write each entry**, not a list of things to emit into the plan. The code examples at the end are illustrations of the reasoning, not a template to paste.

Two rules govern how the entries are used:

- **Produce the entries as part of the plan**, before implementing — so the scan-and-filter is visible and can be reviewed.
- **Then implement each method drift-aware from its entry — this is not a second pass.** The happy path still goes in first *within* each method, but a method is not done until its live drifts are handled. There is no "v1 happy-path, v2 hardening" milestone.

### What each method entry contains

Each entry is a method heading followed by three fields:

- **Core behavior** — one line: what the method does when everything goes right.
- **Drifts handled** — one point per live drift. Each point is **self-contained**: it names what can go wrong, *then* where it's caught (*edge* / *core* / *infra*), *then* how it responds (*reject* / *recover-degrade* / *propagate*) — all in the same point. Keeping those three together per drift is the whole idea; do **not** split them into separate "boundary" and "response" lists, which forces the reader to cross-reference.
- **Left out (why)** — categories that were scanned and deliberately **not** handled, each with a reason and a short verdict (*trust* / *imaginary* / *wrong boundary* / *not live*). Never empty — this field is what proves the scan happened and kept the code from over-engineering.

(*edge / core / infra* are defined under "Handle at the right boundary"; *reject / recover / propagate* under "Every drift gets a deliberate response.")

A worked example of two filled entries is at the end, under Examples.

---

## Core principle: scan wide, handle narrow

Happy-path coding is mostly a *failure to look*, not a failure of technique. So the agent always **looks** across the full drift surface, then **handles** only what is live. Looking is cheap and is the behavior change we want; handling is expensive and is reserved.

The filter applied to every candidate drift:

> **Can this assumption realistically be violated, and would the violation matter? Yes → handle it. No → leave it, and trust the assumption.**

An assumption that can't plausibly break, or whose violation wouldn't matter, is **left alone on purpose**. Writing a guard for it is the over-engineering disease.

**Over-engineering is a defect, equal in weight to happy-path code.** Every guard is also a liability: code to read, maintain, and reason through, and a line that can itself be wrong. A guard against a drift that cannot realistically occur, or a cost no one would pay to prevent, adds noise and false confidence while protecting nothing. When in doubt between adding a guard and trusting an assumption, prefer trusting — and make the trust explicit (the "Left out" field), so the decision is visible rather than accidental.

---

## Finding drift: two faculties

Drift is found two different ways, by two different faculties. The agent uses both.

**1. Technical drift — a standing checklist (generic, mechanical).**
Violations of the machine's rules. These eventually make noise (exceptions, crashes, obviously-wrong values) and are largely domain-independent, so the agent scans them from a fixed list: null / empty, boundary & off-by-one, type mismatch, overflow, timeout, broken connection, malformed data.

**2. Business drift — a surfaced invariant (domain-specific, deferred to the human).**
Violations of the domain's rules: a value that is type-valid but semantically forbidden, a quantity beyond what the domain allows, a state transition the workflow does not permit. These are the **more dangerous** kind because the runtime cannot see them — a semantically invalid value is still a perfectly legal number or string, so nothing throws; the system *succeeds incorrectly* and corrupts data silently. The agent **surfaces** these as explicit preconditions/invariants and **enforces the rules it is given** — but it does not invent domain policy. Business rules require real-world context the agent usually lacks; the domain expert owns them. The agent's job: ask "what domain rule would this operation violate if inputs were hostile?", flag it in the entry, and guard the rule once it's confirmed.

---

## The scan: seven categories

For every operation, the agent walks these seven to **look**. Most operations have only a few that are **live**; the rest are scanned and left alone, and that restraint is correct.

1. **Input** — data from outside, untrusted. Validate at the boundary.
2. **Preconditions / inherited state** — the world the operation inherits: does the referenced record still exist, is the entity in a state that permits this action, has this step already run. Not input, not yet an error — a silent-failure source.
3. **Dependencies** — external calls that error, time out, or return garbage.
4. **Concurrency / shared state** — the assumption that you are the only one acting now: lost updates, double-submits, races. Invisible single-threaded, devastating in production, leaves no trace.
5. **Resources** — the assumption that there's enough: connections, memory, quota. Failures cascade. Usually handled with limits/timeouts/backpressure, often at the infra boundary.
6. **Time** — timeouts, staleness between read and use, expiry, ordering assumptions. A silent variable in almost every operation.
7. **Side-effect completion / atomicity** — the gap between steps: partial writes, non-idempotent retries that double-apply. Guarded with transactions, idempotency, ordering.

A pure in-memory calculation collapses five of seven to nothing. An operation that mutates shared, persisted state lights up almost all of them. The scan is the same; the handling is proportional.

---

## Technical decision-choices carry their own drift

A technical choice — how work is run concurrently, how tasks are managed, a caching layer, a retry policy, a batching strategy — is itself a source of drift, independent of any business rule. Every mechanism has a *default behavior* when the conditions it assumes stop holding, and that behavior is often not what the implementer intended.

The agent reasons in three moves: name **the behavior the choice is meant to produce**, name **the variables that drive it** (a dependency's latency, an independent failure, cache staleness, contention, ordering), then ask **what the mechanism actually does when one of those variables moves**. The gap between intended behavior and default behavior is the drift to record in the entry.

The same restraint governs this as everything else: guard the drift the mechanism *actually* produces under realistic conditions — not imaginary runtime misbehavior, and not failure modes the mechanism cannot exhibit. (Example B shows this concretely.)

---

## Handle at the right boundary

A request moves through layers: it **arrives** at an entry point, flows into the **business logic**, and leans on **shared infrastructure**. A "boundary" is simply the layer where a given drift is caught — and the goal is to catch each drift *once*, at the layer that owns it, so no inner code has to re-check it. This is what keeps the core clean and prevents the same guard from being scattered across every function.

The three boundaries, and what belongs at each:

- **Edge — the entry point where untrusted data first arrives** (the API controller, request handler, message consumer). This is where **input** is validated: types, required fields, ranges, formats. Checked here *once*; everything deeper then **trusts** it and does not re-validate. This is the single biggest lever against null-checks-on-every-line.

- **Core — the business-logic layer where the operation's real work happens.** This is where drifts the logic *itself* owns are handled: **business invariants** (the domain rule the core must enforce), **preconditions** on the state the operation inherited (does the record exist, is the entity in a valid state), and **concurrency/atomicity** around the critical section (a lock, a transaction). These can't be pushed to the edge — they depend on the current state of the system, which only the core sees.

- **Infra — shared, cross-cutting layers outside any single method** (the connection pool, the HTTP client and its timeout, middleware, a circuit breaker, a rate limiter). This is where **resources**, and cross-cutting **dependency/time** concerns, are handled: configured *once* and applied across all callers, not reinvented inside each function.

The test for placement: *"What is the innermost layer that can catch this drift without every caller repeating the check?"* That layer is its boundary.

---

## Every drift gets a deliberate response

For each handled drift the agent picks **one** response, on purpose — this is the response recorded in the drift's point.

- **Reject** — fail fast with a clear, specific error (bad input, violated precondition, broken invariant). The caller gets an actionable signal.
- **Recover** — fallback, default, degrade, bounded retry (transient dependency failure, optional data missing). A degrade is **signaled**, not hidden.
- **Propagate** — let it rise to a layer that can actually decide. Don't handle it here just to look thorough.

**Cardinal sin: never swallow a drift silently.** A caught-and-ignored exception, or a failure turned into a null with no signal, is *worse* than the happy path — the drift is now both unhandled and invisible.

---

## The rules (general, self-applied —  these are useful for the agent to interrogate its own candidate before guarding)

**1. Evidence-of-trigger check — "Have I seen it, or am I inferring it?"**
Before a candidate counts as a gap, ask: *is the thing that would trigger this drift something I have observed in a real sample (a payload, a trace, a log, the actual code), or am I inferring it from how such systems usually behave?* If observed → it can be a gap. If inferred → it is an **unknown**, not a gap. The output for an unknown is *"confirm by observing one real instance,"* **never** *"add a guard."* A guard built on an unobserved trigger may defend the wrong thing entirely.

**2. Prevalence check — "common" justifies looking, never guarding.**
"APIs commonly do X," "this is a known pattern," "most servers…" raises the value of *checking this instance*, not the value of a specific guard in it. Population frequency is not evidence about the case in front of you. Never let *it's common* substitute for *it happens here*. If the only support for a guard is a general-population claim, downgrade it to a one-time check.

**3. Failure-signature check — sort by silent vs. loud before urgency.**
For every candidate, state what the failure *looks like when it happens*:

* **Silent** (wrong-but-confident output, no error, no trace) → fix proactively; it may never otherwise surface. This is the only class that justifies acting *ahead* of observation.
* **Loud & early** (a named error, at or before the boundary, that points at itself) → it will announce itself on first real contact. Prefer to let the real occurrence prove it before hardening. Usually *lower priority, leave until observed.*
  Signature outranks likelihood as the sort key. A likely-but-loud drift is safer to defer than a rare-but-silent one.

**4. De-mask before you handle — the cheap move under uncertainty.**
When a drift is plausible but its trigger is unconfirmed, you are not stuck between "ignore it" and "build full handling." There is a third, cheaper move: **remove the disguise.** Make the uncertain path *fail honestly* (a clear error) instead of *failing silently* (a confident empty / a mislabeled result), without yet building elaborate shape-tolerant handling. De-masking is cheap, correct even under uncertainty, and it's what lets a later real occurrence actually teach you. Reserve the expensive handling for after the trigger is observed. (This is the right read of entry 1: the fix is "stop pretending a parse-miss is an empty result," *not* "parse every possible shape.")

**5. Cost-of-guard check — apply *plausible × matters* to the fix, not just the drift.**
A guard is itself code that can be wrong and must be maintained. Weigh the guard's complexity against the *confirmed* likelihood and stakes of the drift. If the guard is more elaborate than the drift is proven to warrant — a resolver, a broad new branch tree, tolerance for forms you haven't seen — it is over-engineering *inside the fix*. Prefer the smallest intervention (often rule 4's de-mask) over the most complete one.

**6. Ground-it check — point at a line, a sample, or drop it.**
The strongest gaps are provable *now*: a missing timeout, a wait outside a deadline, a cleanup path that doesn't run on cancellation, an inconsistency between two sibling methods. If you can cite either a specific line of code/config **or** an observed real sample, it's a gap. If you can cite neither — only "it could arrive in a shape I don't handle" — you are speculating, and the output is rule 1's *confirm*, not a fix.


---

## Workflow

1. **Understand the operation** and sketch the happy path — the correct success story.
2. **Surface assumptions**: run the technical checklist, and ask the business-invariant question (flag domain rules for the human; don't invent them).
3. **Scan the seven categories** to find which drifts are live for *this* operation.
4. **Filter**: for each candidate, apply *plausible × matters*. The survivors are the entry's handled drifts; the discards go in the "Left out (why)" field.
5. **Write the entry** into the plan — core behavior, then one self-contained point per live drift (what goes wrong → where caught → response), then left-out-and-why. Repeat per method until the entries are the plan.
6. **Then implement each method from its entry** — happy path first within the method, live drifts handled before the method is done. Not a second pass.

---

## Rules

Named checks; apply each with context, not as a recited line.

### Deliverable check — *the per-method entries are the plan artifact*
The agent's output in the plan is one drift entry per method, not written-out drift-handling code. Every entry carries a filled "Left out (why)" field; an empty one means the scan wasn't really done.

### Scan-wide/handle-narrow check — *robust, not paranoid*
Look across all seven categories and both faculties; handle only what passes *plausible × matters*. If a guard defends something that can't realistically break or wouldn't matter, remove it. Over-defense is as much a defect as happy-path code.

### Boundary check — *keep the core clean*
Each drift handled once, where it enters. Untrusted input validated at the edge; interior trusts it. Core-logic guards only for drifts the core genuinely owns. No blanket re-checking layer to layer.

### Deliberate-response check — *no silent swallowing*
Every handled drift resolves to reject, recover, or propagate — chosen on purpose. No ignored exceptions, no failures silently turned into nulls. Degrades are signaled.

### Business-invariant check — *surface, don't invent*
Domain rules are enforced but authored by the domain expert. The agent flags the invariant and guards the confirmed rule; it does not decide policy it lacks the context for.

### Technical-choice check — *drift from the mechanism*
For each significant technical/architectural choice, reason from the behavior it should produce and the variables driving it to the drifts it introduces, and record those specific drifts — not imaginary runtime failures.

---

## Examples

### The per-method drift entry — a filled example

This is what one entry per method looks like in the plan. Each live drift is written as a **single self-contained point** — what can go wrong, where it's caught, how it responds — so you can read it, weigh it, and change the decision without hunting across fields. (The two methods below are implemented in A and B, so you can see how each entry turns into code.)

#### Entry 1 — `transfer(from_id, to_id, amount)`

**Core behavior:** move `amount` from one account to another, all-or-nothing.

**Drifts handled** (each point: *what goes wrong → where caught → response*):

- **Bad input.** `amount` is zero or negative, or the sender and receiver are the same account. → Caught at the **edge** (validated on the way in). → **Rejected** with a specific error (`InvalidAmount` / `InvalidTransfer`); once past the edge, the core trusts the input.
- **Missing or inactive account.** Either account may not exist, or the sender may be inactive. → Checked in the **core** (it depends on current state). → **Rejected** (`AccountNotFound` / `AccountInactive`).
- **Insufficient funds** — a business invariant, given by the domain, not invented. The sender's balance must cover the amount. → Checked in the **core**. → **Rejected** (`InsufficientFunds`).
- **Concurrent transfer or partial write.** Another transfer could touch the same account at the same moment (lost update), or the first write could succeed and the second fail (money leaves one side, never arrives). → Handled in the **core** by doing both reads and both writes inside one transaction with a row lock on each account. → The pair becomes **all-or-nothing and serialized**; on any failure it rolls back.

**Left out (why):**

- Retry on failure — could double-apply the transfer, no clear benefit. *Trust.*
- Type-check on `amount` — the edge already guarantees a number. *Imaginary here.*
- `db is None` check — the connection is wired at startup; it can't drift at runtime. *Imaginary.*
- Resource limits / timeouts — belong at the **infra** layer, not inside this method. *Wrong boundary.*

#### Entry 2 — `get_dashboard(user_id)`

**Core behavior:** assemble a dashboard from three service calls made concurrently.

**Drifts handled** (each point: *what goes wrong → where caught → response*):

- **A dependency call fails.** Any of the three calls can error. → Handled in the **core**, per result. → If the essential one (`user`) failed, the whole request is **rejected** (`UpstreamUnavailable`); if an optional one (`billing`, `activity`) failed, it **degrades** to a safe default and the response is flagged `degraded=True` — never silently empty.
- **A call hangs.** With no time bound, the request is as slow as the slowest call and freezes if one hangs. → Handled in the **core** with a per-call **timeout**. → A slow dependency can no longer freeze the request.
- **`gather`'s default behavior.** On the first failure it propagates immediately and leaves the other two calls running orphaned. → Handled in the **core** by collecting outcomes instead of failing fast (`return_exceptions=True`). → Each call's result is judged on its own; no work is silently discarded.

**Left out (why):**

- Retry — unsafe without idempotency, and it worsens congestion on a slow dependency. *Trust.*
- Circuit breaker — belongs at the **infra** client layer, configured once for all callers. *Wrong boundary.*
- Concurrency guard — these are independent reads with no shared mutable state. *Not live.*

Read an entry as a sentence: *"For this method, these drifts are live, caught at these layers, responding this way — and these were scanned and left out for these reasons."* The **Left out** field is the one reviewers should check hardest: it's where both over-engineering (a guard that shouldn't be there) and under-engineering (a live drift wrongly dismissed) show up.

### A. Business + state + atomicity — Entry 1 implemented

**Happy path** — correct only in the world where every assumption holds:
```python
def transfer(from_id, to_id, amount):
    sender = accounts.find(from_id)
    receiver = accounts.find(to_id)
    sender.balance -= amount
    receiver.balance += amount
    accounts.save(sender)
    accounts.save(receiver)
    return "ok"
```
Silent assumptions: both accounts exist, amount positive, funds sufficient, no concurrent writer, both saves succeed. If the second save fails, money leaves the sender and never arrives — silent corruption, no trace.

**Drift-aware** — happy path kept, surrounded, straight from the entry:
```python
def transfer(from_id, to_id, amount):
    if amount <= 0:                       # input, at the boundary → reject
        raise InvalidAmount(amount)
    if from_id == to_id:
        raise InvalidTransfer("same account")

    with db.transaction():               # technical choice: atomicity + concurrency
        sender = accounts.find_for_update(from_id)   # precondition + row lock
        receiver = accounts.find_for_update(to_id)
        if sender is None or receiver is None:
            raise AccountNotFound                     # reject
        if not sender.active:
            raise AccountInactive(from_id)            # reject
        if sender.balance < amount:                   # business invariant (given, not invented)
            raise InsufficientFunds(from_id)          # reject

        sender.balance -= amount
        receiver.balance += amount
        accounts.save(sender)
        accounts.save(receiver)          # both inside txn → all-or-nothing, no partial transfer
    return TransferResult(from_id, to_id, amount)
```

### B. Pure technical choice — Entry 2 implemented

**Happy path:**
```python
async def get_dashboard(user_id):
    user, billing, activity = await asyncio.gather(
        fetch_user(user_id), fetch_billing(user_id), fetch_activity(user_id),
    )
    return Dashboard(user=user, billing=billing, activity=activity)
```
`gather`'s own behavior is the drift: one failure propagates and orphans the siblings; there's no time bound, so the request is as slow as the slowest call and hangs if one hangs.

**Drift-aware** — reasoned from the mechanism's behavior:
```python
async def get_dashboard(user_id):
    async def bounded(coro):
        return await asyncio.wait_for(coro, timeout=2.0)      # time: ceiling per call

    user, billing, activity = await asyncio.gather(
        bounded(fetch_user(user_id)),
        bounded(fetch_billing(user_id)),
        bounded(fetch_activity(user_id)),
        return_exceptions=True,          # each call fails independently; siblings still finish
    )
    if isinstance(user, Exception):
        raise UpstreamUnavailable("user")         # essential → reject whole request
    billing  = None if isinstance(billing, Exception)  else billing   # optional → degrade
    activity = []   if isinstance(activity, Exception) else activity
    return Dashboard(user=user, billing=billing, activity=activity,
                     degraded=isinstance(billing, Exception) or isinstance(activity, Exception))
```
The mechanism can't know `user` is essential and `activity` optional — that criticality is a design fact the implementer supplies, the same shape as a surfaced invariant.

**The contrast:** happy-path code's fate is set by its weakest input or dependency, and it fails randomly and silently. Drift-aware code either succeeds fully, degrades with a signal, or fails deliberately and namably — handling only the categories genuinely live, and leaving the rest out by design.