---
name: reliable-baseline-spec
description: Use when finalizing one step of a spec and deciding which nuances (business or technical) the first build must address, which can wait for iteration, and which to drop. Triggers include "finalize this step", "what is the baseline for this spec", "which nuances matter", "is this over-engineered", "where do I stop", or a draft spec step with a traceflow and open nuances. Produces a trip (what the step must achieve for its consumer), an annotated traceflow, and one decision card per nuance, then a locked record after the user replies. Do NOT use it to compare alternative approaches (critical analyzer skill), to surface the open choices inside an already-scoped approach (finalize-sub-component-decisions skill), or to write implementation plans.
---

# Reliable Baseline Spec

## 1. Purpose

A spec step can absorb endless nuances. Each one looks reasonable alone, so finalizing never ends. Skipping them all gives a naive solution that fails on ordinary inputs. This skill finds the **reliable baseline**: the smallest spec that handles the common, harmful cases and keeps everything else visible for iteration.

The rule behind it: **build the car the trip needs, not the spaceship.**

A nuance is **found** by walking how the step is built. It is **admitted** to the baseline only if it leads to a failure the step's trip says we cannot tolerate. Everything else is deferred with a trigger, or dropped.

Iteration is part of the method, not a failure of it. Leaving a nuance for later is correct when the failure will be noticed and is cheap to fix. It is wrong when the failure is silent or the fix is expensive.

The skill produces two outputs, in two turns:

- **Part 1: Decision surface.** Trip, annotated traceflow, one card per nuance.
- **Part 2: Locked record.** Produced only after the user replies to Part 1.

---

## 2. Inputs

| Input | Use |
|---|---|
| The step's spec section | What the spec says today. Every card cites it. |
| The step's traceflow | The map for locating nuances and the reading order. If missing, write a skeleton first (Section 4, step 1). |
| **The consumer's spec section** | Required. The trip's consumer and correct output are read from it, never from memory. |
| Locked decisions upstream | Constraints. Never reopened by a card. |
| Code or contracts the step depends on | Source of facts, and of guarantees the step can rely on. |

If the consumer's spec cannot be found, stop and ask for it. A trip written without it is a guess.

---

## 3. The model: three artifacts with three jobs

| Artifact | Job | Question it answers |
|---|---|---|
| **Trip** | The **filter** | Why does this step exist, and what counts as broken for its consumer? |
| **Six parts** | The **discovery checklist** | Where inside the build can a nuance hide? |
| **Traceflow** | The **location and reading order** | At which point in the flow does each nuance act? |

Parts are how nuances are found. The traceflow is how they are shown. The trip decides which ones matter.

### 3.1 The trip

The trip describes the step from the consumer's side. It never mentions tools, prompts, steps, caps or retries.

**Test for every line:** if the step's whole mechanism were replaced, would this line still be true? Yes: trip. No: build, so it belongs in the traceflow.

Six fields, 5 to 10 lines total. Longer means mechanism is leaking in.

| # | Field | Question |
|---|---|---|
| 1 | **Purpose** | What does the consumer get from this step that it would not have without it? If this cannot be stated, raise it as a note: the step may not earn its place. |
| 2 | **Consumer** | Who reads the output and what do they do with it? Also name who does **not** read it, so no card serves an imaginary consumer. Confirmed from the consumer's spec. |
| 3 | **Correct output** | What a right answer looks like from the consumer's side, phrased as a test. "Returns X" restates the mechanism and filters nothing. "Matches what the consumer needs to do Y" is a test. |
| 4 | **Errors and their cost** | A table: each wrong output, what it causes downstream, and whether anyone notices. This is where the asymmetry lives: which mistake is cheap and which is expensive. |
| 5 | **Tolerance** | Which errors the baseline must prevent, which are accepted, and which way to lean when unsure. |
| 6 | **Fixed constraints** | Limits set by the outside world: rate limits, plan quotas, cost ceilings, latency. Limits we chose ourselves are build, not trip. |

Field 3 deserves the most effort. A sharp correct output often points straight at the most important nuance.

### 3.2 The six parts

A part is separate if walking it finds failures the other parts cannot find. Walk each part along the traceflow and ask its questions.

| # | Part | Questions |
|---|---|---|
| 1 | **Inputs** | What actually arrives, and how much does it vary in real use? Missing, malformed, oversized? **Does this step see the same data its consumer will judge by?** |
| 2 | **Business rules** | Which domain truths must hold? Does the output mean what the consumer assumes it means? |
| 3 | **Decision logic** | For each rule or judgment: what happens on borderline or unhandled cases? Which way does it lean when unsure, and does that match the trip's tolerance? |
| 4 | **External dependencies** | How does one call fail (timeout, rate limit, refusal, partial or reshaped response)? What does the dependency already guarantee, so the step does not re-guard it? Which facts about it are unverified? |
| 5 | **Execution flow** | Across many items and over time: partial completion, retries and duplicates, timeouts and cancellation, fan-out against the fixed constraints, shared state and ordering. Does the trip demand concurrency at all? |
| 6 | **Output contract** | Is every outcome an explicit state, with no silent fallback? Which parts of the shape will be hard to change once others depend on it? Does any consumer need a capability the spec restricts? |

**An empty part is a valid result.** Write "no nuances" for it. Never invent a nuance to fill a part.

**Walk existing content too.** The walk covers what the spec already says, not only what it lacks. An existing rule that fails the admission test becomes a **Simplify** card.

---

## 4. Procedure

1. **Traceflow skeleton.** Use the spec's traceflow. If there is none, write 5 to 10 lines: entry, each operation in order, exit. Everything else is placed against it.
2. **Trip.** Read the consumer's spec, then write the six fields. Apply the replace-the-mechanism test to every line.
3. **Walk.** For each part, go down the traceflow and list candidate nuances. Include the neighbour check from Part 1 (Inputs) on every step.
4. **Admission test.** Run Section 5 on every candidate and every existing rule.
5. **Red flags.** Check the result against Section 6.
6. **Write Part 1** (Section 7).
7. **Wait for the reply.** Then write Part 2 (Section 8).

### Stopping rule

The analysis is **done** when every part has been walked against every traceflow point (or marked empty) and every candidate has an outcome. Do not start another round of nuance hunting after that. New nuances enter later only through iteration: tests, real runs and deferral triggers.

---

## 5. Admission test

### 5.1 Grounding gate (first)

A candidate passes only if it names:

- a **row in this step's trip error table** that it prevents, and
- a **line in this step's traceflow** where it acts.

If it cannot name both, it is **Dropped**. This catches nuances carried over from habit or from other specs.

### 5.2 Four factors

| Factor | Question | Verdicts |
|---|---|---|
| **Likely?** | Will ordinary real inputs trigger it? Not "could it ever happen". | Yes / Rare / Unknown |
| **Harmful?** | Does it cause an error the trip's tolerance says to prevent? Cite the error row. | Yes / No |
| **Silent?** | Would anyone notice without going looking for it? | Silent / Loud |
| **Reversible?** | If the baseline gets it wrong, how costly is the fix later? Cheap: local to this step (prompt, internal logic, a constant). Expensive: a shared interface, output contract, stored schema, anything other steps depend on. | Cheap / Expensive |

**Unknown** likelihood: if one cheap probe (a test call, a log query, a look at real data) settles it, probe it, or list it as a verification. Do not guess.

### 5.3 Outcomes

1. **Not harmful** (only causes errors the tolerance accepts): **Drop**.
2. **Harmful and Likely**: **Baseline**. This is what "not naive" means: the baseline handles the common case.
3. **Harmful but Rare or uncertain**: decide by whether iteration can catch it.

| | **Loud** | **Silent** |
|---|---|---|
| **Cheap to change** | **Defer.** Iteration will catch it. | **Signal.** Defer the fix. Build only what makes it visible (a log, an explicit state, a counter). |
| **Expensive to change** | **Shape.** Build the shape now so the later fix breaks nothing. Defer the behavior. | **Baseline.** Iteration cannot save it. |

4. **Existing spec content** whose outcome would be Drop or Defer: **Simplify** (remove or reduce it, and add a Deferred line if it may come back).

### 5.4 Standing rules

- **Restrictions name their cost.** Every "never" or "always" in the spec names who loses which capability. If the trip needs that capability, the restriction is a card.
- **Probe before designing around a fact.** If a position depends on an unverified fact that one cheap probe settles, the probe comes first. A restriction that exists only to avoid answering such a question is a red flag.
- **Unknown failures must surface.** The baseline does not anticipate unknown unknowns. It guarantees they become visible: explicit outcome states, structured logs, no silent fallbacks.
- **Locked decisions are not reopened.** If the trip shows a locked decision causes harm, report it as a note, not a card.
- **Every deferral is written down.** One line: what it is, why it is safe to defer (which cell), and the signal that means it is time to come back.

---

## 6. Red flags

Check the cards against both lists before writing Part 1.

**Spaceship (over-engineering)**
- Judgment edge cases or examples listed in full before any real output exists.
- Robustness for a failure that a guarantee elsewhere already rules out.
- A restriction added to avoid a question one probe could answer.
- Concurrency, caching or batching that the fixed constraints do not demand.
- A rare, loud, cheap-to-fix failure handled in the baseline.

**Naive (under-engineering)**
- A decision judged only inside its own step, never against the consumer's spec.
- A fallback that hides the failure: no log, no explicit state.
- A shared interface shaped only for its current caller.
- A common case named in the trip but not handled.
- "We will iterate" applied to something silent or expensive to change.

---

## 7. Part 1 output: decision surface

Produce these blocks, in this order.

### Block 1: Scope
- **Step reviewed:** name and spec location.
- **Consumer spec read:** name and location.
- **Locked decisions in force:** IDs only.

### Block 2: Trip
The six fields from Section 3.1, with the error table in field 4.

### Block 3: Step map
The traceflow, annotated with card numbers `[n]` at the point where each nuance acts. Mark new operations as new.

### Block 4: Cards, in traceflow order
- Number cards by their position in the flow.
- A nuance about **whether the step should run at all** goes first, at the entry gate.
- **Cross-cutting** nuances (logging, behavior across items, anything that applies throughout) go last, under a "Throughout" heading.
- Same point in the flow: Baseline before Shape, Signal, Defer, Simplify.
- Drops and empty parts do not get cards.

Card template:

```markdown
### [n]. <one-line title>  · <Outcome>
**Part:** <part> · **Traceflow:** <the line where it acts> · **Spec today:** <what the spec says, with line ref, or "not covered">
**Depends on:** <card numbers, or none>

**Scenario:** <concrete input> → <what happens, step by step> → <consequence for the consumer>

| Factor | Verdict | Why |
|---|---|---|
| Likely? | | |
| Harmful? | | <cite the trip error row> |
| Silent? | | |
| Reversible? | | |

**Outcome:** <outcome and the rule in 5.3 that gives it>
**Change:** <what the spec gains, loses or rewords. For Defer, Signal or Shape, the deferral line with its trigger>
**Flip point:** <which factor, if the user disagrees, changes the outcome, and to what>
```

### Block 5: Drops and empty parts
One line each: what was considered and why it was dropped, or "Part n: no nuances".

### Block 6: Notes
Only if any: locked decisions in tension with the trip, contradictions found inside the spec, verifications to probe.

### Block 7: How to read and reply
Include this text for the user:

> 1. Read the trip and the step map once.
> 2. For each card, read the scenario first and ask: does this happen with our real inputs? That is your call on *Likely* and *Harmful*.
> 3. Check the factor table. Mark only the verdict you disagree with.
> 4. The flip point gives the new outcome. No need to re-reason.
> 5. Reply in short form: `3 ✓` · `5 ✗ Likely=Rare` · `2 modify: <change>`.

---

## 8. Part 2 output: locked record

After the user replies:

1. Apply each flipped factor through the grid in 5.3 to get the final outcome.
2. Re-check every card that **depends on** a rejected or modified card.
3. Produce:
   - **Final outcomes:** table of card, outcome, change.
   - **Updated traceflow:** written once, with all accepted changes.
   - **Deferred section:** one line per Defer, Signal and Shape item, ready to paste into the spec.
   - **Verifications:** probes still to run.
   - **Spec edits:** the list of edits to make.

Edit the spec file only when the user asks.

---

## 9. Quality contrasts

These show the quality bar for the fields where quality decides the outcome. **They illustrate quality only. Never carry their content into a card.** Each comes from a different step so no single case dominates.

**Correct output** (trip field 3), from website discovery:
- Weak: "Discovery returns the amenity's website URL, or none."
- Strong: "The URL is the amenity's own official site, or none. A wrong site is worse than none, because a later step scrapes it and scrape evidence overrides web evidence."
- Why: the strong version gives a test, names what the consumer does with it, and exposes the asymmetry.

**Scenario** (card), from a page-selection step:
- Weak: "The LLM may pick the wrong page to scrape."
- Strong: "A hotel's site map returns 50 links. For `pet_policy` the LLM picks `/policies`, but the policy is on `/faq`. The scraped page has no pet text, so the metric reaches resolution with web evidence only and ends null, though the answer was one link away."
- Why: a concrete input, each step visible, and the consequence lands on the consumer.

**Factor reason: Likely?**, from a rate-limited gateway:
- Weak: "Yes. Rate limits happen."
- Strong: "Yes. All pipelines share one key at 10 calls per minute, and one amenity can use 9 (one map, up to 8 scrapes). Two amenities in that stage at once exceed it."
- Why: it argues from the real mechanism and numbers, so the user can check it.

**Factor reason: Harmful?**, from website discovery:
- Weak: "Yes. Bad data."
- Strong: "Yes. Trip error row 'wrong site accepted': a directory page gets scraped as the official source."
- Why: it cites this step's own trip.

**Flip point**, from a search loop:
- Weak: "Depends on the data."
- Strong: "If search timeouts prove rare in practice, Likely becomes Rare and this moves from Baseline to Defer."
- Why: it names the factor, the condition and the new outcome.

---

