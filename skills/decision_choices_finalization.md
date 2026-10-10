---
name: finalize-sub-component-decisions
description: Use this skill when a sub-component already has a finalized (selected) approach and the user needs the remaining decision choices surfaced in a form that can be answered quickly, then locked. Triggers include requests to "list the decisions," "finalize decision choices," "what do I need to decide for this sub-component," or a sub-component spec that has a Goal, Problem, and Selected Approach but no decided details. Do NOT use this skill to compare or choose between approaches (that is the critical analyzer skill), to define or split sub-components (that is the process-flow skill), or to evaluate a sub-component's scope. If no selected approach is provided, the first action is to ask for it, not to guess one.
---

# Finalize Sub-Component Decisions

## 1. Purpose

Take one sub-component whose approach is already chosen, surface every decision still open inside that approach, and present them as a table the user can answer in one pass. After the user answers, lock the decisions into a final record.

This skill produces two outputs, in two turns:

- **Part 1: Decision surface.** The tables and root-cause cards the user answers from.
- **Part 2: Locked decisions.** The final record, produced only after the user answers Part 1.

The goal is speed of decision, not completeness of discussion. The user should be able to read the Decision index, answer D1 to Dn, and be done, opening a root-cause card only when a row is unclear.

---

## 2. Inputs

Read these as fixed constraints. They are not open questions.

| Input | Use |
| --- | --- |
| Sub-component name, Goal, and "Problem It Aims to Solve" | Bounds which decisions are allowed. Every decision must belong to this one problem. |
| **Selected approach** (final) | Defines what is already settled. Rejected approaches are out of scope. |
| Parent component's locked decisions | Constraints. Never re-decide them. |
| Feature Problem Statement and Problem Context | Source of the context-specific decisions. |
| Existing code or contracts, if provided | Source of evidence lines and of facts that need verification. |

If the selected approach is missing or still undecided, stop and ask for it. Do not compare approaches in this skill.

---

## 3. Scoping rules

Apply these before writing anything.

1. **Selected approach only.** Include a decision only if it arises inside the selected approach. Drop any decision that exists only because of a rejected approach.
2. **Settled is not a decision.** A choice the selected approach already determines goes under "Fixed by the selected approach."
3. **Upstream is not a decision.** A choice locked at component level or earlier is not listed. Name it only when a decision depends on it.
4. **One problem.** Every decision must belong to the sub-component's single stated problem. A decision that fits only half of the unit signals a scoping error. Report it as a note to the user and do not add a row.
5. **Facts are not choices.** A question that can only be answered by observing something (a real response shape, a library behavior, a plan limit) is a verification, not a decision.
6. **Cheap and obvious is a default.** When a wrong guess is cheap to fix and one answer is the only reasonable one in this context, put it under Safe defaults, not in the Decision index.
7. **Wording is not a decision.** A wording or coverage gap is fixed in the rewrite. Do not ask the user to decide it.

---

## 4. Part 1 output structure

Produce these five blocks, in this order.

### Block 1: Scope

Three short lines:

- **Reviewed:** the sub-component name.
- **Selected approach:** its name (treated as final).
- **This turn:** Part 1 only.

### Block 2: Fixed by the selected approach

Not questions. One row per settled point.

| Fixed point | Follows from |
| --- | --- |
| One mechanical statement of what is already settled | The selected approach, and the part of it that settles this |

### Block 3: Decision index

This is the evaluation surface. 5 to 8 rows. Add more only if the unit has that many independent choices.

| ID | Decision you must make | Category | Options | Recommended | If unanswered, these findings stay open | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | One choice, phrased as a full question | Generic mandatory / Context-specific | A: ... / B: ... | A, with a short reason | RC1, RC3 | One value from the list below |

Severity is one of: Blocks placement, Blocks input/output contract, Blocks I/O, Breaks a stated guarantee, Changes cost or correctness.

Category meanings:

- **Generic mandatory:** must be decided whenever this kind of sub-component is built, whatever the use case.
- **Context-specific:** matters only because of this feature's Problem Statement, Problem Context, or the parent component's locked decisions.

Row rules:

- Each row is one question. Put the full question in the Decision column so the user can answer D1 to Dn without opening the cards.
- Options are two or three short, mutually exclusive readings. They restate the "Two readings" of the matching card.
- Recommended is the answer that will be built if the user does not override. It must follow from the selected approach and the problem context.
- Sort generic mandatory rows first, then context-specific rows. Within each group, put decisions that block other decisions first.
- Do not batch a second question list later. The Decision index is the only place questions appear in full.

### Block 4: Safe defaults and open verifications

**Safe defaults.** Assumed in the rewrite unless the user overrides. These are not questions. Do not mix them into the Decision index.

| Default | I will assume | Override only if |
| --- | --- | --- |
| Short name | The assumed behavior | The condition that would change it |

**Open verifications.** Facts to observe, not choices.

| ID | What must be verified | How to verify | What changes if the result differs |
| --- | --- | --- | --- |
| V1 | One observable fact | One concrete action | The decision or design element that moves |

Omit either table if it has no rows.

### Block 5: Findings by root cause

One card per root cause, not per section. Cover each Decision index row and each Wording / coverage gap.

Card template:

#### RC#: short name of the root cause

**Kind:** Decision | Contract gap | Wording / coverage

**Defect:** one sentence.

**Two readings:** Reading A / Reading B.

**Why it matters:** what an implementer would build wrongly.

**Closes with:** D# | V# | rewrite only | safe default: name

**Evidence:** one line (method or field name, not a code excerpt).

Card rules:

- Fields as above, then stop. No extra narrative.
- No code blocks. Point at the name, for example: `resolve_category_flags` skips unpaired flags.
- Cite code only when the finding is spec-versus-code and the pointer would be ambiguous without it. Cite the smallest range.
- Root-cause ids (RC1, RC2) are the only numbering. "Issue 1, Issue 2" lists are forbidden.
- A Wording / coverage card may close with "rewrite only" and must not create a Decision index row.
- Do not repeat the same root cause under two cards.

### Held

End Part 1 with one sentence: Part 2 (locked decisions) waits until the Decision index is answered.

---

## 5. Part 2: Locked decisions

Run this only after the user answers.

1. Apply the user's answers to D1 to Dn. Where the user does not answer a row, apply its Recommended value and mark it "assumed."
2. Apply every un-overridden safe default.
3. For each open verification, record its status as Verified (with the observed result) or Pending (with what is blocked).
4. If an answer conflicts with the selected approach or a parent locked decision, stop and flag the conflict. Do not silently resolve it.
5. If an answer to one decision changes another row (for example, a verification result flips a recommended value), restate only the affected rows.

Output a single table:

| ID | Decision | Final answer | Source | Consequence for the build |
| --- | --- | --- | --- | --- |
| D1 | Short restatement of the choice | The chosen option | User / Assumed (recommended) / Safe default | One sentence on what this fixes in the design |

Then list pending verifications, if any, with the decisions each still blocks.

Part 2 does not reopen the approach, add new decisions, or produce new questions. If a genuinely new decision surfaces, report it as one line under the table and wait.

---

## 6. Workflow

1. **Read inputs.** Load the sub-component, selected approach, locked decisions, and context. Ask for the selected approach if it is missing.
2. **Scope.** Apply Section 3 to every candidate decision. Sort each into Fixed, Decision, Safe default, Verification, or Wording.
3. **Check sizing.** If the Decision index exceeds 8 rows, test whether lower-severity rows are really safe defaults.
4. **Research (only if needed).** Consult API docs or SDK references only when a Recommended value cannot be set from the existing contracts. Record anything that cannot be settled by reading as a verification.
5. **Write Part 1.** Produce Blocks 1 to 5, then the Held sentence.
6. **Review.** Check against Sections 7 and 8.
7. **On the user's answers,** produce Part 2.

---

## 7. Rules

- Treat the selected approach as final. Do not compare, re-rank, or reopen approaches.
- Do not re-decide parent or upstream locked decisions.
- Every decision belongs to the one stated problem.
- Every Decision index row has options and a recommended answer.
- Questions appear in full only in the Decision index.
- Do not start Part 2 in the same turn as Part 1.
- Keep the Decision index to 5 to 8 rows unless the unit truly has more independent choices.
- Sort rows by Category, then by whether they block other decisions.

### Anti-patterns

Do not:

- List a decision that only a rejected approach would raise.
- Re-decide something the selected approach or an upstream component fixed.
- Write a verification as a decision, or a decision as a verification.
- Give options with no recommended answer.
- Put cheap, obvious choices in the Decision index instead of Safe defaults.
- Ask the user to decide a wording-only fix.
- Batch questions at the end of the report.
- Treat every row as equal severity.
- Repeat one root cause under several cards.
- Dump code excerpts into the report.
- Open with a walkthrough of every detail of the sub-component.

---

## 8. Explainability rules

1. **No em dashes.** Use periods, commas, or parentheses.
2. **Mechanical, observable language.** Describe what happens, not how it feels.
3. **One claim per sentence** in cards and the Fixed block.
4. **State the mechanism, then the consequence as a separate sentence.**

| Don't | Do |
| --- | --- |
| "creates friction in the pipeline" | "blocks the response" |
| "needs dynamic information" | "depends on request-time data" |
| "The gateway blocks the response, causing delays" | "The gateway blocks the response. This causes delays." |

---

## 9. Worked example (abbreviated)

Copy the surface, not the domain.

**Input fragment.** Sub-component: MCP tool gateway for two servers. Selected approach: `ClientSession` over `streamable_http_client` with a caller-owned `httpx` client. Parent locked: hosted Streamable HTTP with bearer keys.

**Fixed by the selected approach**

| Fixed point | Follows from |
| --- | --- |
| One `ClientSession` per server, entered through an async context stack | Selected approach |
| Caller-owned `httpx` client carries the `Authorization` header | Selected approach |

**Decision index**

| ID | Decision you must make | Category | Options | Recommended | If unanswered, these findings stay open | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Do sessions open at the start of the run and close at its end, or open in a constructor? | Generic mandatory | A: run scope / B: constructor | A, same-task close required | RC1 | Breaks a stated guarantee |
| D2 | Is the gateway a `Protocol` injected into the caller, or a concrete class? | Generic mandatory | A: injected `Protocol` / B: concrete | A, test seam required | RC2 | Blocks input/output contract |
| D3 | Does the connect step check `tools/list` for required tools, or fail at first call? | Context-specific | A: check at connect / B: fail at first call | A, also detects a missing key | RC3 | Changes cost or correctness |
| D4 | Does the crawl parser handle both result shapes, or one? | Context-specific | A: both / B: one | A until V1 is recorded | RC4 | Blocks I/O |

**Safe defaults**

| Default | I will assume | Override only if |
| --- | --- | --- |
| Retry schedule | 2 s then 3 s, transient failures only | You want a different backoff |

**Open verifications**

| ID | What must be verified | How to verify | What changes if the result differs |
| --- | --- | --- | --- |
| V1 | Real `tools/call` response shape from each server | Record one response per server | D4, parser design |

**RC4: crawl result shape is two-valued**

**Kind:** Decision

**Defect:** The crawl call can return final data or a job id, and the contract does not say which shapes the gateway handles.

**Two readings:** The gateway parses both shapes and polls for status on a job id / the gateway parses one shape and fails on the other.

**Why it matters:** A parser built for one shape raises a protocol error mid-run when the server returns the other.

**Closes with:** D4, V1

**Evidence:** `firecrawl_crawl` and `firecrawl_check_crawl_status` are both exposed by the server.

Part 2 (locked decisions) waits until the Decision index is answered.