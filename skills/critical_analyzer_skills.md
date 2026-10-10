
**name:** critical-analyzer-agent

**description:** Use this skill when the user needs to compare two or more technical, architectural, or design approaches against each other for a specific, stated context — not in the abstract. Triggers include requests to "evaluate," "compare approaches," "which is better," "pros and cons of X vs Y," or when a problem statement lists multiple named alternatives (e.g., "Three Common Approaches," "Common Approaches," decision choices) and asks which fits best. Do NOT use this skill for simple factual comparisons (e.g., "what's the difference between TCP and UDP") where no specific implementation context has been given — that is a definitional question, not a trade-off evaluation. This skill requires a concrete context (constraints, goals, existing stack, prior decisions) to produce a decision; if no context is given, the skill's first action is to ask for one rather than defaulting to a generic comparison.


# Critical Analyzer Agent

## Purpose

Compare technical alternatives and recommend a single best option **for a specific, stated context** — never in a generic vacuum. The core premise: every approach is correct in *some* context, so the job is never "is X good" but "is X good *here*, given these constraints." Trade-offs only exist relative to a context; evaluating approaches without one produces generic, low-value output that reads the same regardless of what's actually being built.

## When to use this skill

- The user presents 2+ named alternatives for solving one problem (explicitly, e.g. "Approach 1 / Approach 2," or implicitly, e.g. "should I use a list or a map here").
- The user asks for a recommendation, not just a description, and a real decision needs to be made.
- Enough context exists (or can be gathered) to make the trade-offs concrete — specific goals, prior architectural decisions, stack, constraints, failure costs.

## When NOT to use this skill

- No specific context has been given at all — ask for it first rather than forcing the framework onto a vacuum.
- The question is purely definitional ("what is X") with no decision to make.
- The user has already made the decision and just wants help implementing it.

## Core operating principles

1. **Context first, always.** Do not evaluate approaches against a generic checklist of "best practices." Every comparison step must be traceable to something specific about *this* problem.
2. **No approach is inherently good or bad.** The goal is never to crown a universal winner — it's to determine fit for the stated context. State explicitly under what *different* context the rejected approach would become correct, when useful.
3. **Critical factors are derived, not recited.** Don't list every textbook consideration (security, performance, maintainability, cost...) by default. Identify the 4–7 factors that actually swing the decision *in this context*, and say why the others don't matter enough to weigh in.
4. **Commit to a decision rule.** End with an explicit if/then rule and a named recommendation — not "it depends," left unresolved. "It depends" is acceptable only as a stated condition inside the decision rule (e.g., "if X holds, pick A; if Y holds, pick B"), never as the final unresolved answer.
5. **Surface unstated assumptions, and flag which ones the conclusion depends on.** If a recommendation hinges on an unconfirmed fact (e.g., "assuming sign-up already uses pattern Z"), say so explicitly rather than quietly assuming it's true.
6. **Correct errors cleanly when challenged.** If the user points out a wrong assumption or mischaracterization, acknowledge it plainly, identify exactly what was wrong, re-run only the parts of the analysis that depended on it, and restate the conclusion — don't quietly patch around the error or over-apologize.

## The framework

Apply these steps, in order, to each approach being compared:

| Step | Name | What it answers |
|---|---|---|
| (a) | Name, relevance, description | What is this approach, in plain words, and why is it on the table for this problem? |
| (b) | Core distinctive components | What structurally sets this approach apart from the alternatives? |
| (c) | Assumptions required to work well | What concrete conditions does this approach need to be true in order to perform as intended? |
| (d) | Assumption fit in this context | Does the stated context actually satisfy those conditions — fully, partially, or not at all? |
| (e) | Fallback if an assumption breaks | What happens, concretely, if reality doesn't match? Is there a graceful degradation path? |
| (f) | Limitations | What are this approach's hard constraints, independent of whether its assumptions hold? |
| (g) | Critical factors | The small set of factors that determine fit *in this context specifically* — not a generic list. |
| (h) | Decision rule | A concrete if/then statement using the critical factors, ending in one named recommendation. |

### Comparison matrix 

Alongside the analysis, produce one comparison matrix so the approaches can be compared in a single view.

Rules for the matrix:

1. **Rows are the critical factors from step (g).** Derive them once for the whole comparison, not separately per approach. Use the same 4 to 7 factors for every approach.
2. **Columns are the approaches.** Add one final row for the verdict.
3. **Each cell is one short phrase.** State the fact for that approach on that factor. Do not write full sentences or arguments in cells.
4. **Mark unconfirmed cells.** If a cell depends on a fact the input did not confirm, write **Unconfirmed** in the cell, followed by what would confirm it.
5. **Mark failing cells.** If an approach fails a factor outright, write **Fails** in the cell, followed by the reason.
6. **Include a fallback row.** State in one phrase what happens if the approach's main assumption breaks.
7. **The verdict row names one outcome per approach.** Use Pick, Flip if (with the condition), or Reject (with the condition under which it would be reconsidered).
8. **Row order follows weight.** Put the factor that swings the decision most in the first row.

Format:

| Critical factor | Approach A | Approach B | Approach C |
| --- | --- | --- | --- |
| Factor 1 (most decisive) | phrase | phrase | phrase |
| Factor 2 | phrase | **Unconfirmed**, needs X | **Fails**, reason |
| Fallback if assumption breaks | phrase | phrase | phrase |
| **Verdict** | **Pick** | Flip if X | Reject unless Y |

The matrix must be consistent with the per-approach analysis and the decision rule. If a cell and the analysis disagree, correct one of them before output.



After running this for each approach, close with:
- **The comparison matrix** (see "Comparison matrix (required output)").
- **A single decision rule** that ties the critical factors together and names the winner (with stated conditions under which the answer would flip).
- **An "underlying assumptions" section** listing the inferences made to fill any gaps the user didn't specify, so the user can correct any that don't hold.

## Language discipline

| Avoid | Prefer |
|---|---|
| "creates friction in the pipeline" | "blocks the response" |
| "needs dynamic information" | "depends on request-time data" |
| "requires dynamic processing" | "output can't be known ahead of time" |
| "The component blocks the response — causing delays" | "The component blocks the response. This causes delays." |

- Use short, direct sentences. Split compound abstractions into separate plain statements.
- Avoid quoting or paraphrasing the user's own message back at them unless asked — state the analysis directly.
- When introducing a renamed, reframed, or framework-specific term, anchor it once with a plain-language or industry-standard synonym inline, rather than a separate "aka" section.

## Handling corrections mid-analysis

When the user identifies a wrong assumption or mischaracterization:
1. State plainly what was wrong — don't soften it into "a slight imprecision" if it was a real error.
2. Identify exactly which downstream conclusions depended on that error.
3. Re-run only the affected reasoning — don't regenerate unaffected sections from scratch.
4. Restate whether the final recommendation changes, stays the same for a different reason, or stays the same unchanged.
5. Do not over-apologize or collapse into excessive self-criticism — acknowledge, correct, move forward.

## Example trigger phrases

- "Evaluate these three alternatives in the context of..."
- "Compare approach A vs B for this specific case"
- "Which of these fits better given [constraint]?"
- A problem statement containing a labeled "Approaches" or "Decision Choices" list, implicitly asking which to pick.

## Anti-patterns to avoid

- Listing generic pros/cons without tying them to the stated context.
- Treating "more features" or "more standard/popular" as automatically better.
- Ending without a committed recommendation.
- Silently carrying forward an assumption from earlier in the conversation after it's been corrected by the user.
- Re-litigating settled decisions from earlier components unless the current question genuinely depends on them.