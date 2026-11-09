---
name: persistence-schema-designer
description: Design database tables, fields, constraints and read/write policies for checkpoint-based persistence in any feature workflow, using a layered MVP framework.
---

# Persistence Schema Designer

Design the persistence layer for a feature workflow (tables, fields, identity, rules, write/read policies, lifecycle) so the workflow can resume after a crash or failure without losing progress or repeating side effects.

## How to apply this skill

- Every table, field, constraint and policy must be **derived from the feature being designed**, through the layers below. Nothing is included because it appears in this skill.
- Blocks labeled **Example** only illustrate how a rule is applied. They are not templates, defaults or required content. Do not copy their names, fields or structure unless the feature's own inventory justifies each item.
- Names used in this skill (`run`, `step`, `run_id`, `step_id`, `status`, etc.) are generic terms for the concepts below. Use the naming conventions of the project being designed.

## Terminology

- **Run:** one execution of the workflow, from trigger to finish, including all its retries.
- **Step:** one unit of work inside a run that takes an input and produces an output.
- **Checkpoint:** the saved record of one step's status and output within a run.

## Context and defaults

- Scale: MVP. Priority: storage and resumability over analytics.
- One relational database (PostgreSQL unless stated otherwise). Metadata in columns, step payloads in a JSON column (JSONB in PostgreSQL). No separate JSON store.
- Choose the simplest design that satisfies the rules below. Defer anything only analytics would need.

## Inputs required

Before designing, collect:

1. The list of workflow steps, in order.
2. For each step: inputs, outputs (shape and approximate size), the external service it calls (if any), and whether it changes anything outside the system.
3. How the workflow is triggered and executed (single process, queue/workers, HTTP request, scheduled) and how retries happen.
4. Whether any data contains personal or sensitive information.

If any input is missing, ask for all missing items in one message before proceeding. Never invent steps.

## Procedure

Work through the layers in order. Each layer uses the outputs of the previous ones.

### Layer 0: Data inventory

For each step, record: step identifier, what it generates, its step type, and who reads the data later.

Step types:

- **LLM call:** expensive, non-deterministic.
- **Read-only API:** changes nothing outside the system.
- **Side-effecting API:** changes something outside the system. Test: running it twice changes something twice.
- **Deterministic:** cheap, same result every time.

Classification rules:

- Classify by the operation performed, not by the provider. The same provider can offer both read-only and side-effecting operations.
- Standard LLM calls (prompt in, response out) are not side-effecting.
- If an LLM requests tool executions that the workflow carries out, each tool execution is a separate step, classified on its own.
- If an LLM API creates objects stored on the provider's side, that call is side-effecting.
- Quota usage and cost are not side effects.

> **Example (illustration only):**
> - A call that fetches records from an external service → read-only API.
> - A call that sends a message or creates a record in an external service → side-effecting API.
> - Parsing or formatting data already in memory → deterministic.

Rule: persist LLM, read-only API and side-effecting API steps. Do not persist deterministic steps; they must be recomputable from persisted outputs.

### Layer 1: Access patterns

List the exact reads the feature performs, derived from how it resumes and how it guards side effects:

- **Resume lookup:** required for any resumable workflow. Defines how the feature retrieves the checkpoints of a run to decide where to continue.
- **Idempotency lookup:** required only if Layer 0 contains side-effecting steps. Defines how the feature checks whether an action already happened.
- **Other reads:** include only if the feature actually performs them, and state which step or component performs each one.

Do not design columns or indexes for analytics queries; data is stored in full and can be indexed later without breaking anything.

### Layer 2: Schema

**Tables**

- Identify the entities from Layers 0-1. A resumable workflow has at least a run-level entity and a step-level entity.
- Create a table per entity whose facts would otherwise repeat across rows. Do not create tables that no access pattern or rule needs.

**Normalization**

- Each fact is stored in one place only; other tables reference it through keys, never copy it.
- A column belongs to the table whose entity it describes: run-level facts only in the run table, step-level facts only in the step table.
- Tables are linked through foreign keys (the step table references the run table), never through copied columns.
- Values stored as columns are never repeated inside JSON payloads.
- Do not split JSON payloads into separate tables.
- Stop at this level for MVP.

**Column vs JSON (decide per field)**

- **Column** if the database must enforce it, the feature filters or looks up by it, or it is updated on its own.
- **JSON** otherwise (mainly step outputs).

**Identity**

- **Row identity:** primary key of each table.
- **Business identity:** run identifier + step identifier, unique together.
- **Action identity:** idempotency key, unique, only for side-effecting steps. Derive it deterministically from run identifier + step identifier; generate it once and save it before the call.
- The run identifier is generated once per run and reused on every retry.

**Fields**

Derive fields from these categories. Include a field only if a layer above justifies it, and record the justification:

| Category | Purpose | Include when |
|---|---|---|
| Identity | Primary key, run identifier, step identifier | Always |
| Status | Current state of a run or step | Always |
| Action identity | Idempotency key | Side-effecting steps exist |
| Error | Error type, whether retryable | Failures must be classified for retry decisions |
| Payload | Step output as JSON, or a reference to object storage | Step output must be reused on resume |
| Version | Workflow version | Resume must detect workflow changes |
| Timestamps | Created and updated time | Needed for detecting stuck steps or ordering |
| Other | Anything else | A specific access pattern or rule requires it |

> **Example (illustration only, not a required field set):**
> A run table with an identifier, workflow version, status and timestamps; a step table with an identifier, run identifier, step identifier, status, idempotency key, error fields, JSON output and timestamps. The actual fields depend entirely on the feature's inventory.

### Layer 3: Rules

- **Database enforces:**
  - Primary keys and foreign keys.
  - Uniqueness of run identifier + step identifier.
  - Uniqueness of the idempotency key, if side-effecting steps exist.
  - `NOT NULL` on required metadata.
  - Allowed status values (`started`, `completed`, `failed`).
- **Code enforces:** one validation model per step's JSON payload, applied before write and after read; business rules.
- Reason: uniqueness cannot be guaranteed in code under concurrency, and the database cannot validate JSON contents.

### Layer 4: Write policies

Apply per step, based on its type from Layer 0:

- **LLM and read-only API steps:** write after the call: `completed` + output.
- **Side-effecting steps:** before the call: `started` + idempotency key; after the call: `completed` + result.
- **On error:** `failed` + error type + whether retryable.
- **Atomic write:** output and `completed` status are saved in a single write.
- **Status transitions:** only `started -> completed`, `started -> failed`, `failed -> started`. A `completed` record is never changed.
- **Concurrency:** inserts rely on unique constraints; status updates are conditional on the current status. A rejected insert or an update that changes no rows means another execution owns the step: stop that execution.
- **Large payloads:** above a size threshold stated in the design, store in object storage and keep only the reference.

### Layer 5: Read policies

- `completed`: skip the step, load its saved output.
- `started`: the step was interrupted.
  - Side-effecting: verify with the external service (idempotency key, or a lookup if the service does not support keys) before redoing.
  - Otherwise: rerun.
- `failed`: retry only if retryable; otherwise stop and report.
- No record: run the step normally.

### Layer 6: Lifecycle

- **Versioning:** store the workflow version at run level and a schema version inside each JSON payload. On mismatch with the current workflow, restart the run instead of resuming.
- **Retention:** keep checkpoints after completion; they serve as basic history for later evaluation.
- **Sensitive data:** state whether personal data in payloads is stored as is, redacted, or deleted after a set period.

## Output format

Keep the output precise and concise. Produce, in this order:

1. **Schema summary** (at the top):
   - **Tables:** each table with a one-line description of the entity it holds.
   - **Primary keys:** per table.
   - **Foreign keys:** each relationship (referencing table and column → referenced table and column).
   - **Business identity keys:** per table, the unique combination that identifies a record in business terms (for example, run identifier + step identifier).
   - **Action identity keys:** the idempotency key and the steps it applies to, if side-effecting steps exist.
   - **Indexes:** each index, its columns, and the Layer 1 lookup it serves.
2. Step inventory table (step, type, generates, persisted yes/no, read by).
3. Access patterns list, each linked to the step or component that performs it.
4. For each table: fields table (field, type, column or JSON, constraint, justification).
5. Database constraints and code-level validations.
6. Write policy per persisted step.
7. Resume (read) policy.
8. Lifecycle decisions.
9. SQL DDL for all tables, including constraints and indexes for the Layer 1 lookups.
10. Assumptions and open questions.

## Final check

Before delivering, confirm:

- Every table, field and rule traces back to the feature's inventory or access patterns, not to an example in this skill.
- Every persisted step has a write policy; every unpersisted step is deterministic and recomputable.
- No fact appears in two tables; no column value is duplicated inside JSON.
- Every column is justified by enforcement, lookup or independent update.
- If side-effecting steps exist: each has an idempotency key, a uniqueness constraint on it, and a duplicate-check path.
- Run identifier + step identifier is unique.
- Status transitions are defined and `completed` is immutable.
- Nothing was added only for analytics.