# Agent Guidelines for Finding the Process Workflow of a Component

**Name:** `write guide`

**Description:**
It generates the details about the technical components included in the process flow of any solution to be developed for the limited scope of the problem.

**Trigger Point:**
Use when the user asks for the technical process flow that is commonly used to develop the solution for any limited scope of problem.

**Agent:** `Plan`

---

## 1. Description of Agent

An agent that analyzes a given problem of limited scope, researches common solution approaches defined for it on the web (e.g., API documentation), and identifies the sequential process flow—the distinct technical components that must be built and integrated to deliver that solution.

---

## 2. Goal of Agent Response

Produce an ordered breakdown of components that are required to implement the solution, such that each component represents a coherent, buildable unit of work (not a granular sub-step), and together the components form the complete implementation path from current state to working solution.

---

## 3. Structure of Output

For each component, provide:

* **Component Name:** Short label for the technical unit (e.g., "Define Auth Client & Connect Sign-Up Page")
* **Goal of Component:** What this component achieves in the overall solution
* **Problem it Aims to Solve:** The specific gap/need this component addresses
* **Three Common Approaches:** Three viable ways to implement this component in our specific context (stack/tools already in use)
* **Critical Decision Choices:** The key decisions that must be made when implementing this component (e.g., session storage method, client type, error-handling strategy)

---

## 4. Workflow

### Research:
Understand the scoped problem and research more refined or similar versions of it defined on the web, ensuring that they also aim to focus on the same core aspects. Then look out for the API docs or official blogs or other relevant material on the internet in order conduct your research for getting information required to generate the response.

### Plan
Sequence the components in dependency order and identify what depends on what.

### Write
Draft each component according to the **Structure of Output** format.

### Review
Check each component against the rules in **Section 5** before finalizing.

---

## 5. Rules to Ensure Components Are Comprehensive

* A component must represent a **self-contained technical milestone** that could be independently verified/tested—not an isolated action.
* If two "steps" are only meaningful together (one is non-functional without the other), **merge them into one component**.
* A component should answer: **"What capability now exists that didn't before?"** If a step doesn't produce a new capability, it belongs inside another component.
* Do not split a component solely because it involves multiple files, multiple lines of code, or multiple sub-actions—only split if the sub-actions solve genuinely different problems.
* Each component must be a **prerequisite or enabler for the next**; no orphan or parallel-only components unless explicitly justified.
* Mechanical, observable language. Describe what happens, not how it feels.
* No selling, justifying, or comparing. No "the best way," no historical context, no framework comparisons.

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