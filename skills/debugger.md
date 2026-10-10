---
name: failure-cause-finder
description: Use when an agent must find the cause of a backend error or failure from the code, the logs, and the error message. Drives a disciplined backward trace from the symptom to the first explicit failure — the earliest point where the program itself signaled it broke, with only healthy execution upstream — and produces a transparent, lean investigation trace the user can read through their own context. Finds where the cascade began; it does not judge semantic correctness or apply a fix.
---

# Failure Cause Finder

An agent uses this skill to locate the **cause** of a failure, starting from three inputs: the **code**, the **logs** (as produced by the logging skill), and the **error message**. The goal is a disciplined path to the cause — not roaming, not guessing, not changing code to see what happens.

This skill directs *what to pursue and in what order*. The agent's own harness *executes* each step — reading files, pulling logs, searching the codebase, running a probe. The skill decides the next move; the harness performs it.

The discipline in one line:

> **The symptom you're handed is the last victim. The cause is the first explicit failure — the earliest point the program signaled it broke, with only healthy execution upstream. Trace backward to it, confirm it, report it. Don't fix it, and don't judge what a value *should* have been.**

---

## Core principle: find the first explicit failure

A failure cascades: one break produces downstream breaks. The error you start with is the *last* victim, almost never the cause. Classify every point on the path by its **explicit** signals — not by judging whether a value is semantically right (that judgment needs domain knowledge and belongs to the user):

- **Innocent** — ran normally, signaled nothing.
- **Victim** — failed explicitly, but because an *earlier* failure fed it.
- **Cause** — the first explicit failure: it broke while everything feeding it had run normally.

"Explicit" means the program itself declared the failure — a raised exception, an error return / `ToolFailure`, a logged degrade/recover WARN, a crash. Those are observable without deciding what was *correct*. The cause is the earliest such signal in the chain.

Two expectations bound the work:

- **The cause is confirmed, not plausible.** The first explanation that fits is a hypothesis to *falsify*, never a conclusion to act on. Making the symptom disappear is not finding the cause.
- **The skill stops at the first explicit failure.** *Why* that point failed on healthy inputs is often a semantic question — that is the user's to answer, and the fix is a separate activity. This skill locates where the cascade began and hands off.

---

## How to confirm the first explicit failure: check the inputs, not the universe

"Nothing upstream also failed" is a global negative you cannot prove by auditing all upstream code. Prove a **local positive** instead: an upstream failure could only reach this point *through one of its inputs*, so if every input arrived healthy, the failure originated here.

At each candidate point, ask one question:

> **Are all of this point's inputs healthy?**
> - **Yes** → the failure was born here. First explicit failure. Confirmed.
> - **No** — an input is itself a failure-product → this point is a victim; move to the producer of that input and ask again.

This walks **one hop at a time** and terminates: each unhealthy input moves you strictly upstream until inputs are all healthy.

**Healthy vs. failure-product is an explicit check, never a semantic one.** An input is a *failure-product* only if it carries a failure marker: a propagated exception, an error/`ToolFailure` passed down, a sentinel/`None`/empty produced by a logged degrade, or a value an upstream step *raised or logged a failure* producing. Otherwise it is *healthy* — well-formed, arrived via a path with no failure signal. The agent never asks "is this value correct?"; it asks "did it arrive via a failing path?"

**Enumerate the full input surface** — declared inputs **plus hidden inputs**: shared/mutable state read, globals, time, external reads. An upstream failure can feed a point through shared state without touching its parameters. Checking only declared parameters is how a victim gets wrongly crowned as the origin.

**Settle each input with the cheapest sufficient evidence, in order:**
1. **Logs** — walk the correlation id's trail backward; it was built to carry boundary values, degrades, and state changes, so provenance is often already recorded.
2. **Code** — read the input's producer for a path that emits a failure/sentinel under the observed conditions.
3. **Reproduction** — only if logs and code are inconclusive, under the reproduction rules below.

**Confirm by trying to break it.** To claim a point is the origin, actively search its full input surface for a failure-fed input. The claim stands only if that search comes up empty — confirmation is the *failure of falsification*, not the first healthy input you see.

---

## Reproduction and the sandbox

Reproduction is gated by **cost**, and all of it is isolated:

- **Cheap / pure-CPU, no side effects** → reproduce freely; probe, re-run, narrow as needed.
- **Costly** (spends money, hits an external dependency, has side effects, is slow) → reproduce **at most once**. Plan that single run so it captures everything needed; you will not get a second.
- **All reproduction and probing happen in one dedicated scratch/test file.** Real files are **read-only** throughout the investigation. The agent does not modify production code until the cause is confirmed and it has moved to fixing — a separate activity outside this skill. This structurally prevents "change something and see if the symptom goes away."

---

## Detect the failure's shape first — it decides the method

Before tracing, determine which shape the failure is, because the backward trace only applies to one:

- **In-request cascade** — a failure and its victims within one run's path (an exception with a trace, one correlation id). → Backward-trace that correlation id to the first explicit failure. The primary method.
- **Emergent / cross-request** — resource exhaustion, leaks, races; the symptom appears in code that is obviously innocent, failures cluster in time, or shared/accumulated state is involved. → The first explicit failure lives in *another* run or in accumulated state, **not** in the failing request's path. Backward-tracing this one request chases a victim forever. Switch to looking across runs / at the accumulated state.

Misreading the shape is the main way this skill wastes effort. Decide it explicitly, up front.

---

## Workflow

1. **Classify the failure** — its reproduction cost (free / one-shot / log-only) and its shape (in-request vs. emergent).
2. **Pull the trail** — reconstruct the failing run from its correlation id; that ordered path is what you trace. (For an emergent failure, gather the cluster of related failures instead.)
3. **Start at the symptom** — the last victim. Identify its full input surface.
4. **Trace backward** — at each point, classify every input as healthy or failure-product (logs → code → reproduction). An unhealthy input moves you to its producer; bisect long suspect chains by checking a midpoint. All probing in the scratch file; real files read-only.
5. **Confirm the origin** — a point whose full input surface is all healthy but which failed explicitly. Try to falsify it before accepting it.
6. **Report** — the first explicit failure, its evidence chain, and the handoff. No fix.

---

## Rules

Named checks; apply each with context.

### First-explicit-failure check — *symptom is the last victim*
Trace to the earliest point the program *explicitly* signaled failure with healthy execution upstream. Never treat the starting error as the cause; never substitute "a value looks wrong" (semantic) for "the program signaled a failure" (explicit).

### Input-surface check — *prove a local positive*
Confirm an origin by showing its full input surface — declared **and** hidden (shared state, globals, time, external reads) — arrived healthy. Never try to audit all upstream code. An input is unhealthy only if it carries an explicit failure marker, not if its value merely looks off.

### Falsification check — *confirmed, not plausible*
Actively search for a failure-fed input before declaring an origin. The first fitting story is a hypothesis; a vanished symptom is not a confirmed cause.

### Shape check — *trace the right thing*
Decide in-request vs. emergent before tracing. Don't backward-trace a single request whose symptom is a victim of conditions set in other runs or accumulated state.

### Sandbox check — *real files read-only*
All reproduction and probing live in the dedicated scratch file. Reproduce costly failures at most once. Change no production code until the cause is confirmed and you are fixing — which is outside this skill.

### Ceiling check — *report the boundary honestly*
If an input's provenance can't be settled from logs or code and can't be reproduced, do not claim a clean origin. Report the earliest *confirmed* explicit failure and name the unverified input as an open gap.

### Scope check — *locate, don't adjudicate or fix*
The deliverable is a confirmed first explicit failure plus its evidence chain. *Why* it failed on healthy inputs (semantic) is the user's; the fix is a separate activity.

---

## Output: a lean, transparent investigation trace

The output *is* the trace of checks, symptom → origin — not a report written afterward, and not everything the agent read. Only checks that moved the scope appear. Two properties make it readable through the user's own context: every check separates **Found** (fact, not contestable) from **So** (inference, contestable), and every elimination carries *why* that point was healthy.

**Symptom** — one or two lines: the error and where it surfaced (the last victim).

**The trace** — ordered checks, each:
- **Why checked** — what led here from the previous step.
- **Looked at** — logs / code @ file:line / reproduction (tag the cost).
- **Found** — the factual observation; evidence only.
- **So** — verdict: *eliminated* (healthy — why) / *implicated* (unhealthy → trace to ⟨next⟩) / *inconclusive* (provenance unestablished). Mark ⚠ if it rests on something unverified.

**Conclusion**
- **First explicit failure** — the point; one line: healthy inputs in, explicit failure out, with evidence.
- **Cascade** — origin → victim → … → symptom, in one line.
- **Handoff (your call)** — the semantic *why* past the origin, stated as the specific open question that is the user's.
- **For your lens (unverified)** — the 1–3 things the agent relied on but couldn't confirm, each with "if your context says otherwise, the origin moves to ⟨where⟩." These are where the user's external knowledge is decisive.

---

## Example (specific — the real shape varies)

This shows the *form*, not a template. A real investigation may have more hops, an emergent shape, a one-shot or log-only reproduction, or an unresolved ceiling — handle what the case presents.

> **Symptom** — `TypeError: 1 - None` at `apply` (checkout, req 7a3f). Last victim.
>
> **Check 1 — the `rate` input to `apply`**
> - **Why checked:** the error names `rate=None`; `rate` is `apply`'s input, so trace it.
> - **Looked at:** logs (req 7a3f trail).
> - **Found:** a `pricing_degraded` WARN earlier in the same trail — `rate` was produced as `None` by a timeout fallback.
> - **So:** *implicated* — `rate` arrived as a failure-product (a degrade), not healthy. `apply` is a victim; trace to the degrade.
>
> **Check 2 — the degrade in `fetch_discount_rate`**
> - **Why checked:** it produced the unhealthy `rate`.
> - **Looked at:** logs (the WARN) + code (`fetch_discount_rate`, timeout branch).
> - **Found:** the pricing call raised `Timeout`; the `except` returned `None`. Its only input, `user_id`, arrived well-formed; the sole failure feeding this point is the external timeout.
> - **So:** *first explicit failure* — the pricing `Timeout`. Healthy input in, explicit failure born here, nothing upstream failed.
>
> **Conclusion**
> - **First explicit failure:** `pricing_client.get_rate` timed out in `fetch_discount_rate` (req 7a3f). Evidence: `pricing_degraded` WARN + the `Timeout`.
> - **Cascade:** timeout → fallback returns `None` → `None` into `apply` → `TypeError`.
> - **Handoff (your call):** the degrade *chose* `None` as its fallback; whether that (vs. a safe default) is correct is a design decision — yours.
> - **For your lens (unverified):** I treated `user_id` as healthy because it was well-formed in the request, and could not see the pricing service internals — *if* the timeout was itself triggered by something we sent, the origin moves upstream to that producer.