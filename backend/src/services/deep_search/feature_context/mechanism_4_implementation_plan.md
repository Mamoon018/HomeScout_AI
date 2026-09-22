# Deep Search — Mechanism 4 Implementation Plan

Mechanism 4 of the **User Requirement Interpretation** responsibility: after Mechanism 2
has written `state.resolved`, one constrained LLM call proposes zero to two taxonomy nodes
from persona evidence. Exact-node collisions are stripped in code. Survivors are stamped
with `category_id` and written to a new `inferred_categories` field. Distinctness Step 1
aliases and all of Step 2 live only in the instruction. Inference is methods on the existing
responsibility class — no new class layer.

Architecture and modularity decisions live in
[mechanism_4_architecture_decisions.md](mechanism_4_architecture_decisions.md).

Locked decisions: input is the `RequirementInterpretationState` after Mechanism 2
(`state.resolved` is set); one constrained call, always; empty `inferred_categories` is
valid; cap of two is schema-only (`maxItems: 2`); no truncate, no pad; wire fields are
`taxonomy_node` and `reasoning` only; `category_id` is stamped after strip; exact-node
collision is stripped and never raises; unknown taxonomy node rejects the whole body;
distinctness Step 1 aliases and all of Step 2 are instruction-only; `inferred_categories` is
a new list on the state, not mixed into `resolved_explicit_categories`; `interpret()` calls
this after `run_explicit_category_resolution`; schema name is `inferred_categories_schema`;
empty default is `[]`; tests are pytest with a dummy provider; a live sample runner
seeds post-Mechanism-2 state and does not re-call Mechanisms 1 or 2.

## Explicitly out of scope

- **Mechanism 3 is not implemented.** When it lands, `interpret` inserts it between
  Mechanism 2 and Mechanism 4. This slice does not read Mechanism 3 output.
- **No `DeepSearchFeature` class.** Only Responsibility 1 exists; `interpret` is the
  coordinator.
- **No programmatic distinctness clamp.** Aliases and Step 2 stay in the instruction.
- **No characteristics, `raw_name`, `provenance`, or priority** on inferred entries.
- **No leftover-flag resolution, depth, or metrics.**
- **No new LLM provider, persistence, route, or repository.** The handoff stays in-process.

---

# 1. File and Module Structure

Placement follows the live layering already in the service: contracts in `feature_schemas/`,
prompt content in `feature_prompts/`, workflow in `requirement_interpretation.py`, error
semantics in `exceptions/`, tests in `backend/tests/`, dev scripts in `feature_sample_runs/`.
LLM SDKs stay in `clients/`. No new `utils/`, route, repository, or client file. No file
exists per stage — Mechanism 4 extends the same class in the same file as Mechanisms 1 and 2.

### New files — this slice adds 3 source files

| File | Owns | Contains |
| --- | --- | --- |
| [feature_prompts/inference_instruction.py](../feature_prompts/inference_instruction.py) | M4 prompt text | task, evidence, distinctness, negation, 6 pairs, `build_inference_instruction` |
| [tests/services/deep_search/test_mechanism_4_inference.py](../../../../tests/services/deep_search/test_mechanism_4_inference.py) | assembled-path fixture set | dummy provider; empty, strip, stamp, reject-body checks |
| [feature_sample_runs/category_inference_sample_run.py](../feature_sample_runs/category_inference_sample_run.py) | live M4 sample | seeded post-M2 state; stage-by-stage print; one inference call |

### Modified files

| File | Change |
| --- | --- |
| [feature_schemas/schemas.py](../feature_schemas/schemas.py) | wire models, schema name, schema builder, `InferredCategory`, `inferred_categories` on state |
| [requirement_interpretation.py](../requirement_interpretation.py) | add M4 workflow and stages; rewire `interpret` after Mechanism 2 |
| [exceptions/deep_search.py](../../../exceptions/deep_search.py) | add `InferenceError` base + `InferenceProviderError`, `InferenceValidationError` with `stage` |

No new composition-root file: `create_requirement_interpretation(settings)` is unchanged.
Taxonomy access (`AMENITY_TAXONOMY_NODES`, `TAXONOMY_NODE_SET`, `render_taxonomy`) is reused,
not rebuilt.

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| `InferenceService` / `Mechanism4` class | methods on `UserRequirementsInterpretation` | locked rule; stages share the responsibility's providers |
| `inference_contracts.py` module | fields in the one `schemas.py` | all service contracts stay in one place, as in M1 and M2 |
| Distinctness validator in code | instruction text only | spec: aliases and Step 2 are not a programmatic clamp |
| Parameterize `_assert_nodes_in_taxonomy` | inline `TAXONOMY_NODE_SET` check in execute | helper logs 2A events and raises 2A errors |
| Retry / backoff layer | none | invalid body rejects the whole response; 2B coverage retry does not apply |
| Merge prompt into `category_resolution_instruction.py` | own `inference_instruction.py` | 2A owns mapping/resolution; inference rules change independently |
| `DeepSearchFeature` coordinator class | `interpret` sequences M4 after M2 | only Responsibility 1 exists; Mechanism 3 is out of scope |
| Re-call M1/M2 inside the M4 sample | seeded post-M2 state | earlier mechanisms are already sampled |

---

# 2. Architecture and Modularity Decisions

See [mechanism_4_architecture_decisions.md](mechanism_4_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation — raw input → per-category specification
   ├─ Mechanism 1 Workflow: parse_unstructured_input — unstructured input → extracted buckets
   ├─ Mechanism 2 Workflow: run_explicit_category_resolution — map, maybe clarify, re-resolve
   └─ Mechanism 4 Workflow: run_persona_driven_category_inference — persona facts → 0..2 inferred nodes
      ├─ (contract) InferredCategoriesResult schema — see §B, not a runtime method
      ├─ Stage 2: build_inference_instruction — evidence, distinctness, taxonomy, six pairs
      ├─ Stage 3: execute_category_inference — one call → valid body or typed error
      ├─ Stage 4: write_inferred_categories — strip exact-node dups, stamp ids, write state
      └─ (harness) dummy-provider path checks — test-only, not in request path
```

The schema is a **contract** (§B). The fixture set is **test-only** and excluded from §E.
Sub-component 1 does not become a runtime method. There is no `DeepSearchFeature` node
because only Responsibility 1 exists.

## B. Data Contracts

All of these live in [feature_schemas/schemas.py](../feature_schemas/schemas.py), except the
error types in [exceptions/deep_search.py](../../../exceptions/deep_search.py).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `InferredCategoryEntry` | one wire proposal | `taxonomy_node: str` — taxonomy node · `reasoning: str` — non-empty persona-fact evidence | wire model | Stage 3 → Stage 4 |
| `InferredCategoriesResult` | batched wire body | `inferred_categories: list[InferredCategoryEntry]` — `maxItems: 2`, empty allowed | wire model | Stage 3 → Stage 4 |
| `InferredCategory` | stored inferred entry | `taxonomy_node: str` · `category_id: int` — stamped in code · `reasoning: str` | dataclass, written once | Stage 4 → later mechanisms |
| `RequirementInterpretationState` *(extended)* | mutable workflow state | existing fields plus `inferred_categories: list[InferredCategory]` (default `[]`) | **mutable** — Stage 4 assigns the list | M2 → M4 → later mechanisms |
| `InferenceError` | M4 failure base with `stage` | `message: str` · `stage: str` — default `execute_category_inference` | immutable | Stage 3 → caller |
| `InferenceProviderError` | no provider returned a body | inherits `InferenceError` | immutable | Stage 3 → caller |
| `InferenceValidationError` | body failed schema or unknown node | inherits `InferenceError` | immutable | Stage 3 → caller |

Rules surfaced here: empty list is `[]`, not omitted and not `None`; closed schema
(`additionalProperties: false`); `category_id` is absent from the provider schema; no
`characteristics`, `raw_name`, `provenance`, or priority on inferred entries;
`INFERRED_CATEGORIES_SCHEMA_NAME = "inferred_categories_schema"`; exact-node overlap is not
a validation failure.

`inferred_categories_json_schema()` derives from `InferredCategoriesResult`, reuses
`_apply_strict_object_rules` and `_inject_taxonomy_node_enum`, and does not strip
`category_id` (the wire model never has it).

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol *(reused)* | `generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict [raises: LLMProviderError]` | `OpenAIStructuredProvider`, `GroqStructuredProvider` | Stage 3 |
| `inferred_categories_json_schema` | schema derivation | `() -> dict` — strict schema, taxonomy enum, `maxItems: 2` | one | Stage 2, Stage 3 |
| `build_inference_instruction` | function | `(json_schema: dict) -> str` — task, rules, taxonomy, six pairs | one | Stage 2 |
| `TAXONOMY_NODE_SET` / `render_taxonomy` | taxonomy data *(reused)* | membership set; numbered node list for the instruction | one (`amenity_taxonomy.py`) | Stage 2, Stage 3 |

No new provider. Composition root unchanged. Why the protocol is reused lives in the
architecture file.

## D. Class and Method Blueprint

**`UserRequirementsInterpretation`** — in
[requirement_interpretation.py](../requirement_interpretation.py). Mechanism 4 adds the
methods below. Existing M1 and M2 methods stay. The class holds the same injected
`StructuredLLMProvider` chain.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `interpret` | `(raw_input: str) -> RequirementInterpretationState [raises: InferenceProviderError, InferenceValidationError]` | sequence parse, Mechanism 2, then Mechanism 4 |
| `run_persona_driven_category_inference` | `(state: RequirementInterpretationState) -> RequirementInterpretationState [raises: InferenceProviderError, InferenceValidationError] [mutates: state.inferred_categories]` | drive stages 2→4 for one request |
| `build_inference_instruction` | `(json_schema: dict) -> str` | assemble evidence, distinctness, taxonomy, pairs |
| `execute_category_inference` | `(state: RequirementInterpretationState, instruction: str) -> InferredCategoriesResult [raises: InferenceProviderError, InferenceValidationError]` | constrained call, then independent body validation |
| `write_inferred_categories` | `(state: RequirementInterpretationState, body: InferredCategoriesResult) -> None [mutates: state.inferred_categories]` | strip collisions, stamp ids, write list |

**Module-level functions**

| Function | Module | Signature | Purpose (one line) |
| --- | --- | --- | --- |
| `inferred_categories_json_schema` | `feature_schemas/schemas.py` | `() -> dict` | strict inference schema, taxonomy enum, cap two |
| `build_inference_instruction` | `feature_prompts/inference_instruction.py` | `(json_schema: dict) -> str` | inference instruction assembly |
| `_render_inference_user_content` | `requirement_interpretation.py` | `(state: RequirementInterpretationState) -> str` | JSON dump of persona, explicit nodes, payload |
| `_call_providers` *(reused)* | `requirement_interpretation.py` | `(*, instruction, user_content, json_schema, schema_name, stage, provider_error_cls=CategoryMappingProviderError) -> tuple[dict, str] [raises: provider_error_cls]` | try providers in order; raise the given error class |

`interpret` calls `parse_unstructured_input`, then `run_explicit_category_resolution`, then
`run_persona_driven_category_inference`. It does not call Mechanism 3.

## E. Runtime Flow — Data Object Journey

Test harness excluded — not in the request path.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `parse_unstructured_input` | `raw_input: str` | state with `extracted` | `resolved=None`, `inferred_categories=[]` |
| 2 | `run_explicit_category_resolution` | state (`extracted`) | `state.resolved` | explicit `taxonomy_node` + `characteristics` present |
| 3 | `build_inference_instruction` | `inferred_categories_json_schema()` | `instruction: str` | state unchanged |
| 4 | `execute_category_inference` | state, instruction, providers | `InferredCategoriesResult` **or** typed error | state unchanged; `resolved.*` untouched |
| 5 | `write_inferred_categories` | body, explicit nodes, extracted ids | `state.inferred_categories` | zero to two stored entries, or `[]` |

**Transformation trace (shape only):**

```
RequirementInterpretationState{ payload, extracted, resolved=None, inferred_categories=[] }
 → state.resolved = ResolvedRequirements{ resolved_explicit_categories[], persona_facts[], ... }
 → (+ inference instruction, + json_schema)
 → dict                                                                # raw body, local to stage 4
 → InferredCategoriesResult{ inferred_categories: [{taxonomy_node, reasoning}, ...] }
   | InferenceProviderError | InferenceValidationError                 # stage 4 exits
 → inferred_categories: [InferredCategory{taxonomy_node, category_id, reasoning}, ...]
   | []                                                                # empty body, or full strip
 → return state
```

**Approach at the real decision points:**

- The call always runs, including when `persona_facts` is empty. There is no skip branch.
  Empty `[]` is a valid body.
- Providers are tried in the bound order: primary (OpenAI) first; Groq only if the primary
  fails to return a response. Which provider is primary is decided at the composition root,
  not inside this stage (see the architecture file).
- The schema constrains the output at generation time (taxonomy enum, `maxItems: 2`, closed
  objects). The first returned body is then validated as an independent second check against
  `InferredCategoriesResult`.
- Validation is all-or-nothing: extra keys, missing or empty `reasoning`, or more than two
  entries reject the whole response. Count is not clamped in code.
- After schema accept, every `taxonomy_node` is checked against `TAXONOMY_NODE_SET`. Any
  unknown node rejects the whole body. Exact-node overlap with the explicit set is not a
  validation failure.
- Two distinct exits, each naming the stage: `InferenceProviderError` when no provider
  returned a body; `InferenceValidationError` when the body failed schema or the
  taxonomy-set check.
- User content is a JSON dump of persona facts, each explicit `{taxonomy_node,
  characteristics}`, and payload. The full taxonomy is already in the instruction.
- Strip walks the validated list in order. An entry whose `taxonomy_node` equals a resolved
  explicit node is dropped (`exact_explicit_duplicate`). A later inferred entry that repeats
  an earlier inferred node is dropped (`duplicate_inferred_node`). Collision is logged and
  does not raise. Survivors (zero, one, or two) are written. Empty list after a full strip
  is success.
- `category_id` is stamped only after the strip: next integer after
  `max(extracted.explicit_categories.category_id)`, or `0` when that list is empty. Ids are
  not taken from `resolved_explicit_categories` only. `resolved_explicit_categories` is not
  mixed with inferred entries.

## F. Method Detail

**`run_persona_driven_category_inference`**

- **Purpose:** sequence instruction, call, and write for one request.
- **What it does:** require `state.resolved` (set by Mechanism 2); build instruction;
  execute; write; return the same state. No skip when persona is empty.
- **Inputs:** state after Mechanism 2 · **Outputs:** same state · **Failure:** Stage 3 typed
  errors.

**`build_inference_instruction`**

- **Purpose:** make one call return zero to two distinct nodes with evidence-citing
  `reasoning`.
- **What it does:** concatenate task statement, evidence rule (generic association is not
  enough; cite persona facts; `reasoning` is not a Mechanism 3 purpose-reason), distinctness
  Step 1 (same node / alias / synonym / trivial rewording → omit) and Step 2 (reconstruction,
  discrimination, directionality; any yes → omit), negation rule, negative rules (do not
  invent nodes; do not force a category when evidence is thin; return `[]`), full taxonomy
  render, closed schema, and six worked pairs on maintained node strings: empty persona →
  `[]`; one valid distinct node; exact-node collision omitted; negation omitted; two distinct
  nodes; Step 2 overlap (`gym` / `fitness_center`).
- **Inputs:** `json_schema` · **Outputs:** `str` · **Failure:** none.

**`execute_category_inference`**

- **Purpose:** return a schema-valid body whose nodes are in the taxonomy, or a typed
  failure.
- **What it does:** take user content from persona facts, explicit `{taxonomy_node,
  characteristics}`, and payload; send instruction as the system message; try providers in
  the bound order; validate the first body against `InferredCategoriesResult`; schema
  failure rejects with no retry; then reject the whole body if any node is outside
  `TAXONOMY_NODE_SET`; do not strip exact-node overlap; do not write state; do not clamp
  count.
- **Inputs:** `state`, `instruction` · **Outputs:** `InferredCategoriesResult` · **Failure:**
  `InferenceProviderError` (no provider answered), `InferenceValidationError` (schema or
  unknown node).

**`write_inferred_categories`**

- **Purpose:** drop identity collisions, stamp ids, persist the inferred list.
- **What it does:** take the explicit node set from
  `state.resolved.resolved_explicit_categories`; walk the wire list in order; drop and log
  `exact_explicit_duplicate` and `duplicate_inferred_node`; compute the next id from
  `state.extracted.explicit_categories`; stamp `InferredCategory` rows on survivors only;
  assign `state.inferred_categories` even when empty; leave `resolved.*`, `persona_facts`,
  `payload`, `extracted`, and `user_responses` untouched.
- **Inputs:** `state`, `body` · **Outputs:** none · **Failure:** none (collision is not a
  request failure).

---

# 4. Sample Runner and Dummy-Provider Fixture Set

Neither check is part of the request path in §E. No new settings.

## 4.1 Live sample runner

From `backend/`:

`python -m src.services.deep_search.feature_sample_runs.category_inference_sample_run`

It seeds a Mechanism-2-style `RequirementInterpretationState` (`state.resolved` set;
`swimming_pool` and `book_store` mapped; persona facts about a rescue dog and a third-trimester
pregnancy; restaurants negated). The seed does not reuse the inference few-shot inputs
(gym/supermarket, child_care_agency, pharmacy, nightlife, fitness_center). Mechanism 1 and Mechanism 2
are not called. One live inference call.

It builds the responsibility through `create_requirement_interpretation(get_settings())`,
then calls the Mechanism 4 stage methods in sequence rather than
`run_persona_driven_category_inference`, printing a titled section after each:

| Section printed | Content |
| --- | --- |
| `INPUT STATE` | seeded payload, extracted, resolved; confirms `inferred_categories` starts `[]` |
| `STAGE 2 - SCHEMA` | `inferred_categories_json_schema()`; `maxItems: 2`; no `category_id` |
| `STAGE 2 - INSTRUCTION` | inference instruction in full; taxonomy and few-shot counts |
| `STAGE 3 - USER CONTENT` | JSON dump of persona facts, explicit nodes + characteristics, payload |
| `STAGE 3 - PROVIDER ATTEMPTS` | one line per attempt; then the raw decoded body |
| `STAGE 3 - VALIDATED` | `InferredCategoriesResult` via `model_dump_json(indent=2)` |
| `STAGE 4 - INFERRED CATEGORIES` | stored `InferredCategory` rows after strip and id stamp |
| `STAGE 4 - RESOLVED UNCHANGED` | `state.resolved` snapshot equality after write |

Execute discards the raw body once the typed contract exists, so the runner attaches a
collecting log handler and reads attempt lines and the raw body off
`DEEP_SEARCH_LOGGER_NAME` (`category_resolution.*` events, filtered by
`execute_category_inference`). On a typed failure it catches `InferenceError`, prints the
class, its `stage`, and the message, and exits non-zero.

## 4.2 Dummy-provider fixture set

The pytest file is a dev check. No real provider calls. Dummy provider pattern matches
[test_mechanism_2_clarification.py](../../../../tests/services/deep_search/test_mechanism_2_clarification.py).
State is seeded as after Mechanism 2 (`resolved` set).

From `backend/`:

`pytest tests/services/deep_search/test_mechanism_4_inference.py`

It constructs `UserRequirementsInterpretation` with a fake `StructuredLLMProvider` whose
`generate_structured` returns a recorded dict. It runs the real validate, strip, stamp, and
write path.

| Check | Asserts |
| --- | --- |
| empty persona → `[]` | `inferred_categories == []`; no exception |
| one valid distinct node | one stored entry; `category_id` is `max(extracted ids) + 1` |
| two valid distinct nodes | two stored entries; ids consecutive after that max |
| one collision plus one sibling | sibling kept; collision logged; no exception |
| both collide → `[]` | `inferred_categories == []`; no exception |
| two inferred entries, same node | first kept; later dropped |
| unknown taxonomy node | `InferenceValidationError`; list stays `[]` |
| more than two entries | `InferenceValidationError`; body not truncated |
| no explicit categories | numbering starts at `0` |
| instruction-only (Step 2, negation, thin evidence) | dummy body already obeys; stored list matches; code did not clamp |
