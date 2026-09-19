# Agent Guidelines for finding Process flow of a Component

**Name:** `write component process flow`

**Description:**

generates details about technical sub-components included in process flow required to implement a **SPECIFIC, ALREADY-SELECTED approach** for a **SPECIFIC component** of a mechanism — where that component was itself previously identified as part of process flow of a feature. Generation happens **WITHIN use-case-specific core aspects defined in Problem Statement & Problem Context**, AND within finalized scope of component (goal, problem it solves, critical decisions already locked at component level).

**Trigger:**

when user asks for technical process flow needed to actually build a component, given component already defined (name, goal, problem) and one of three previously proposed approaches finalized/selected.

**Plan agent:**

Input problem statement/context + finalized component-level info + selected approach. Analyze what specific approach requires to be fully built; research web for common/reference implementations of that approach (API docs, standard patterns, SDKs/libraries); identify sequential technical sub-components to deliver component using selected approach only.

**Goal:**

ordered breakdown of sub-components required to implement selected approach; each coherent/buildable unit, not granular sub-step; together complete implementation from current state to fully working component via chosen approach.

**Output per sub-component:**

* **Component Name**
* **Goal of Component**
* **Problem it Aims to Solve**
* **Three Common Approaches** (viable ways to implement sub-component in specific context, consistent with parent selected approach)
* **Critical Decision Choices**
* Bring generic mandatory decisions + context-specific decisions made relevant by problem/context/locked component decisions
* Locked component decisions are fixed constraints; do not reopen, downstream choices stay consistent.

**Workflow:** Research → Plan → Write → Review.

**Rules:**

* self-contained technical milestone independently verifiable/testable
* merge steps that are only meaningful together
* component should produce new capability
* don’t split by files/lines/sub-actions, only genuinely different problems
* each sub-component prerequisite/enabler for next; no orphan/parallel unless justified
* full set must implement selected approach in entirety, nothing from unselected approaches
* don’t contradict/re-decide component-level locked decisions
* if prerequisite sub-component missing, include in correct order
* “sub-components” are concrete technical work units needed to build one selected approach, analogous to feature mechanisms→components.

**Explainability Rules**

6. **No em dashes.** Use periods, commas, or parentheses instead.
7. **Mechanical, observable language.** Describe what happens, not how it feels.
8. **No selling, justifying, or comparing.** No "the best way," no historical context, no framework comparisons.

| Don't                                                | Do                                                       |
| ---------------------------------------------------- | -------------------------------------------------------- |
| "creates friction in the pipeline"                   | "blocks the response"                                    |
| "needs dynamic information"                          | "depends on request-time data"                           |
| "requires dynamic processing"                        | "output can't be known ahead of time"                    |
| "The component blocks the response — causing delays" | "The component blocks the response. This causes delays." |

9. **Bridge new framework terms with legacy or generic vocabulary in `description` and intro.** Guides win or lose SERPs on the colloquial query (e.g. "next js form submission", "next js api endpoint", "next js error page"), not on the framework's preferred noun. When the guide covers a renamed or differentiated concept, include one synonym (Pages-era term, REST/web term, or industry-standard label) in the frontmatter `description` and once in the introduction. Fold into prose. No separate "Synonyms" or "Also known as" section.

| Don't                                            | Do                                                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| "Learn how to use Route Handlers"                | "Build API endpoints (formerly API Routes) with Route Handlers"                                               |
| "Learn how to mutate data with Server Functions" | "Submit forms and update data with Server Functions, the App Router approach to form posts and API mutations" |