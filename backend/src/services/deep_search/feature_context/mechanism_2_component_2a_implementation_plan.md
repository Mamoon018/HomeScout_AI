# Deep Search — Mechanism 2 Component 2A Implementation Plan

Mechanism 2, Component 2A (Category Scope & Ambiguity Resolution) of the **User Requirement
Interpretation** responsibility: two constrained LLM operations that turn the raw categories
and flags from Mechanism 1 into taxonomy-mapped `ResolvedCategory` entries. **Operation 1**
(taxonomy mapping) always runs; **Operation 2** (category-flag resolution) runs only when
`user_responses` is present on the state. It reuses the `StructuredLLMProvider` seam
introduced in Mechanism 1 and adds methods to the same responsibility class — no new class
layer.

Architecture and modularity decisions live in
[mechanism_2_component_2a_architecture_decisions.md](mechanism_2_component_2a_architecture_decisions.md).

Locked decisions: Operation 1 **always runs**, Operation 2 is **gated** on `user_responses`;
`user_responses` is a **phrase-keyed mapping** (not a list); all `AmbiguityFlag` fields are
**required, default `None`**; taxonomy is **inlined in full** and mapping is **constrained by
enum** to real nodes; one **single LLM call per operation**; characteristics are attached
**programmatically** by exact `raw_name` equality; Mechanism-1 flags are merged as a **union,
no dedup**; every category flag exits Operation 2 resolved (confident or nearest-node).

## Explicitly out of scope

- **The Router (Category Resolution Check) is not implemented.** 2A produces the
  `ResolvedRequirements` the router would inspect; the branch itself is a later step.
- **Component 2B (Category Clarification Questions) is not implemented.** 2A only *reads*
  `user_responses`; 2B is what *writes* it. The field is added now because 2A branches on it.
- **No third pass, no retry/backoff.** One call per operation; an out-of-contract body is a
  contract violation, rejected — not retried elsewhere.
- **No dedup of the merged flag set.** The Mechanism-1 flag union is intentional.
- **No persistence, route, or repository.** The handoff stays an in-process mutable state.

---

# 1. File and Module Structure

Placement follows the live layering already in the service: contracts in `feature_schemas/`,
prompt content in `feature_prompts/`, workflow in `requirement_interpretation.py`, error
semantics in `exceptions/`, dev scripts in `feature_sample_runs/`. No file exists per
operation or per stage — 2A extends the same class in the same file as Mechanism 1.

### New files — 2A adds 3 source files

| File | Owns | Contains |
| --- | --- | --- |
| [feature_schemas/amenity_taxonomy.py](../feature_schemas/amenity_taxonomy.py) | Sub-component 3: the maintained taxonomy as data | `AMENITY_TAXONOMY_NODES: tuple[str, ...]` (478 nodes), `TAXONOMY_NODE_SET: frozenset[str]`, `render_taxonomy()` |
| [feature_prompts/category_resolution_instruction.py](../feature_prompts/category_resolution_instruction.py) | Sub-components 4 & 5 prompt text | task statements, mapping/resolution rules, worked pairs, `build_taxonomy_mapping_instruction`, `build_flag_resolution_instruction` |
| [feature_sample_runs/category_resolution_sample_run.py](../feature_sample_runs/category_resolution_sample_run.py) | manual run entry point, terminal output | `SAMPLE_STATE` builder, first-pass and second-pass runs, `main()` |

### Modified files

| File | Change |
| --- | --- |
| [feature_schemas/schemas.py](../feature_schemas/schemas.py) | Sub-component 1 & 2 contracts: enrich `AmbiguityFlag`; add `UserResponse`, `user_responses`, `ResolvedCategory`, `ResolvedRequirements`, `resolved`; add Op1/Op2 wire models + strict schema builders |
| [feature_prompts/extraction_instruction.py](../feature_prompts/extraction_instruction.py) | Sub-component 1 ripple: instruct Mechanism 1 to emit `category`/`characteristic` on every flag; update the four worked-example outputs |
| [requirement_interpretation.py](../requirement_interpretation.py) | add Component 2A methods to `UserRequirementsInterpretation`; sequence the first pass in `interpret` |
| [exceptions/deep_search.py](../../../exceptions/deep_search.py) | add `CategoryResolutionError` base + `CategoryMappingProviderError`, `CategoryMappingValidationError` with `stage` attrs |

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| `Component2A` / per-operation classes | methods on `UserRequirementsInterpretation` | locked rule; a mechanism is methods that share the responsibility's providers |
| `resolved_requirements.py` new module | fields in the one `schemas.py` | all service contracts stay in one place, as in Mechanism 1 |
| `taxonomy/` package + loader | one `amenity_taxonomy.py` | one flat list of nodes; no retrieval, no asset engine |
| separate Op1 and Op2 prompt modules | one `category_resolution_instruction.py` | both operations belong to Component 2A; content, not logic |
| `ResolvedRequirements` as standalone return | field `resolved` on the state | spec: it *becomes part of the state*, updated in place across passes |
| Router / 2B files | none | out of scope this mechanism |

---

# 2. Architecture and Modularity Decisions

See [mechanism_2_component_2a_architecture_decisions.md](mechanism_2_component_2a_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation — raw input → per-category specification
   └─ Mechanism 2 Workflow: resolve_explicit_categories — raw categories/flags → resolved taxonomy entries
      ├─ Op 1 · Stage 1: build_taxonomy_mapping_instruction — mapping rules + full taxonomy + schema
      ├─ Op 1 · Stage 2: execute_taxonomy_mapping — one constrained call → two arrays or typed error
      ├─ Op 1 · Stage 3: assemble_resolved_requirements — attach chars, merge M1 flags, copy persona/payload
      ├─ Gate: (branch) user_responses populated? — skip Op 2 when empty
      ├─ Op 2 · Stage 4: build_flag_resolution_instruction — resolution rules + {flag,response} pairs + taxonomy
      ├─ Op 2 · Stage 5: execute_flag_resolution — one constrained call → resolved entries or typed error
      └─ Op 2 · Stage 6: merge_resolved_flags — add entries, drop every category flag, in place
```

The Gate is the one node that is not a method; it is a branch inside the workflow method. The
Router and 2B have no node — out of scope. There is no `DeepSearchFeature` node because only
Responsibility 1 exists.

## B. Data Contracts

All of these live in [feature_schemas/schemas.py](../feature_schemas/schemas.py), except the
taxonomy constants in [feature_schemas/amenity_taxonomy.py](../feature_schemas/amenity_taxonomy.py).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `AmbiguityFlag` *(enriched)* | one flag Mechanism 1 or Op1 emits | `phrase: str` · `target: Literal["category","characteristic","persona"]` · `category: str \| None` · `characteristic: str \| None` | wire model | M1 / Op1 → 2A |
| `UserResponse` | one clarification answer 2B wrote | `question: str` · `response: str` | wire model | 2B → Op2 |
| `RequirementInterpretationState` *(extended)* | the mutable workflow state | `payload: PayloadRecord` · `extracted: ExtractedRequirements` · `user_responses: dict[str, UserResponse]` (default `{}`) · `resolved: ResolvedRequirements \| None` (default `None`) | **mutable** | M1 → 2A → router |
| `ResolvedCategory` | one taxonomy-mapped category | `taxonomy_node: str` · `raw_name: str` · `characteristics: list[str]` · `provenance: Literal["confident","nearest_node"]` | in state | Op1/Op2 → router |
| `ResolvedRequirements` | 2A's output object on the state | `payload: PayloadRecord` · `resolved_explicit_categories: list[ResolvedCategory]` · `ambiguity_flags: list[AmbiguityFlag]` · `persona_facts: list[str]` | **mutable** — Op2 appends | Op1 → Op2, router |
| `MappedCategory` | one Op1 confident mapping (wire) | `taxonomy_node: str` (enum) · `raw_name: str` | wire model | provider → Stage 3 |
| `TaxonomyMappingResult` | Op1 call output (wire) | `resolved_categories: list[MappedCategory]` · `ambiguity_flags: list[AmbiguityFlag]` | wire model | Stage 2 → Stage 3 |
| `ResolvedFlagEntry` | one Op2 resolution (wire) | `taxonomy_node: str` (enum) · `raw_name: str` · `provenance: Literal["confident","nearest_node"]` | wire model | provider → Stage 6 |
| `FlagResolutionResult` | Op2 call output (wire) | `resolved_categories: list[ResolvedFlagEntry]` | wire model | Stage 5 → Stage 6 |

Rules surfaced here: enriched-flag fields are required so an empty value arrives as `null`,
not an omitted key (`extra="forbid"` still holds); `resolved` is the only field 2A creates and
the object Op2 mutates in place; `taxonomy_node` on both wire outputs is `enum`-constrained to
`AMENITY_TAXONOMY_NODES` so a returned node is always a real node; the model returns *only*
`raw_name` + `taxonomy_node` (+ `provenance` in Op2) — characteristics, persona, payload, and
M1 flags are handled programmatically.

`taxonomy_mapping_json_schema()` and `flag_resolution_json_schema()` derive from the wire
models, reuse `_apply_strict_object_rules` to close every object, and inject the taxonomy
`enum` onto each `taxonomy_node`.

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol *(reused)* | `name`, `model`, `generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict [raises: LLMProviderError]` | `OpenAIStructuredProvider`, `GroqStructuredProvider` | Stage 2, Stage 5 |
| `render_taxonomy` | function | `() -> str` — full node list for prompt inlining | one | Stage 1, Stage 4 |
| `TAXONOMY_NODE_SET` | constant | `frozenset[str]` — defensive node-membership check | one | Stage 3, Stage 6 |
| `taxonomy_mapping_json_schema` | schema derivation | `() -> dict` — strict Op1 schema with node enum | one | Stage 1, Stage 2 |
| `flag_resolution_json_schema` | schema derivation | `() -> dict` — strict Op2 schema with node enum | one | Stage 4, Stage 5 |

No new abstraction: 2A reuses the provider chain already bound on the class by
`create_requirement_interpretation`.

## D. Class and Method Blueprint

**`UserRequirementsInterpretation`** — in [requirement_interpretation.py](../requirement_interpretation.py).
Component 2A adds the methods below to the existing class; they read the same state and
provider chain as Mechanism 1.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `resolve_explicit_categories` | `(state: RequirementInterpretationState) -> RequirementInterpretationState [raises: CategoryResolutionError]` | Mechanism 2 workflow; Op1 always, Op2 when gated |
| `build_taxonomy_mapping_instruction` | `(json_schema: dict) -> str` | assemble mapping rules, negative rules, full taxonomy, worked pairs |
| `execute_taxonomy_mapping` | `(state, instruction: str) -> TaxonomyMappingResult [raises: CategoryMappingProviderError, CategoryMappingValidationError]` | one constrained call, then validate independently |
| `assemble_resolved_requirements` | `(state, mapping: TaxonomyMappingResult) -> ResolvedRequirements` | attach chars, handle match-fail, merge M1 flags, copy persona/payload |
| `resolve_category_flags` | `(state) -> None [raises: CategoryResolutionError]` | gate on `user_responses`; drive Op2 and mutate `state.resolved` |
| `build_flag_resolution_instruction` | `(json_schema: dict) -> str` | assemble resolution rules, nearest-node rule, full taxonomy |
| `execute_flag_resolution` | `(pairs: list[tuple[AmbiguityFlag, UserResponse]], instruction: str) -> FlagResolutionResult [raises: CategoryMappingProviderError, CategoryMappingValidationError]` | one constrained call over {flag,response} pairs |
| `merge_resolved_flags` | `(state, result: FlagResolutionResult) -> None` | append resolved entries, drop every category flag, in place |

**Module-level functions**

| Function | Module | Signature | Purpose (one line) |
| --- | --- | --- | --- |
| `render_taxonomy` | `feature_schemas/amenity_taxonomy.py` | `() -> str` | render all nodes for prompt inlining |
| `taxonomy_mapping_json_schema` | `feature_schemas/schemas.py` | `() -> dict` | strict Op1 schema with node enum |
| `flag_resolution_json_schema` | `feature_schemas/schemas.py` | `() -> dict` | strict Op2 schema with node enum |
| `build_taxonomy_mapping_instruction` | `feature_prompts/category_resolution_instruction.py` | `(json_schema: dict) -> str` | Op1 instruction assembly |
| `build_flag_resolution_instruction` | `feature_prompts/category_resolution_instruction.py` | `(json_schema: dict) -> str` | Op2 instruction assembly |

`interpret` gains one line: after `parse_unstructured_input`, it calls
`resolve_explicit_categories` for the first pass (Op2 self-skips with empty `user_responses`).

## E. Runtime Flow — Data Object Journey

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `build_taxonomy_mapping_instruction` | `taxonomy_mapping_json_schema()`, taxonomy | `instruction: str` | state unchanged |
| 2 | `execute_taxonomy_mapping` | state (`extracted`, `payload`), instruction, providers | `TaxonomyMappingResult` **or** typed error | two arrays: `resolved_categories[]`, `ambiguity_flags[]` |
| 3 | `assemble_resolved_requirements` | state, mapping | `state.resolved = ResolvedRequirements` | `resolved_explicit_categories[]` + merged flags + carried persona/payload |
| 4 | *(gate)* | `state.user_responses` | branch | Op2 skipped when empty |
| 5 | `build_flag_resolution_instruction` | `flag_resolution_json_schema()`, taxonomy | `instruction: str` | state unchanged |
| 6 | `execute_flag_resolution` | category flags paired with responses, instruction, providers | `FlagResolutionResult` **or** typed error | `resolved_categories[]` with provenance |
| 7 | `merge_resolved_flags` | state, result | mutates `state.resolved` | category flags removed; entries appended |

**Transformation trace (shape only):**

```
RequirementInterpretationState{ payload, extracted, user_responses={}, resolved=None }
 → (+ mapping instruction, + json_schema)
 → dict                                                    # raw Op1 body, local to stage 2
 → TaxonomyMappingResult{ resolved_categories[], ambiguity_flags[] }
 → state.resolved = ResolvedRequirements{ payload, resolved_explicit_categories[], ambiguity_flags[], persona_facts }
   |  (user_responses empty) → first pass final: category flags may remain
   |  (user_responses present):
       → dict                                              # raw Op2 body, local to stage 6
       → FlagResolutionResult{ resolved_categories[] }
       → state.resolved  (resolved_explicit_categories += Op2 entries; category flags removed)
    | CategoryMappingProviderError | CategoryMappingValidationError            # stage 2 / stage 6 exits
```

**Approach at the real decision points:**

- Operation 1 always runs; Operation 2 runs only when `state.user_responses` is non-empty —
  the gate is the single branch in the workflow method.
- One call per operation sees all raw categories (Op1) or all {flag, response} pairs (Op2) at
  once, so cross-category context informs each mapping; partial failure is handled at assembly.
- `taxonomy_node` is `enum`-constrained at generation time; `TAXONOMY_NODE_SET` re-checks it as
  an independent second check, mirroring Mechanism 1's validate-after-constrain rule.
- Post-Op1 assembly runs in a fixed order: attach characteristics by exact `raw_name` match →
  a `raw_name` with no match becomes a `target:"category"` flag (`phrase = raw_name`) →
  Mechanism-1 flags appended as a union → persona/payload copied unchanged.
- Op2 pairs each `target:"category"` flag with its `user_responses[phrase]` entry explicitly;
  the model does not look responses up. Every flag exits with a node — `"confident"` when the
  response gives evidence, `"nearest_node"` otherwise — so zero category flags survive.
- A validation failure does **not** fall back to the next provider; an out-of-contract body is
  a contract violation. Two typed exits name their cause and carry a `stage`.

## F. Method Detail

**`assemble_resolved_requirements`**

- **Purpose:** turn Op1's two arrays into the full `ResolvedRequirements` on the state.
- **What it does:** for each `MappedCategory`, exact-matches `raw_name` against
  `extracted.explicit_categories` and copies that category's `characteristics` onto a
  `ResolvedCategory` with `provenance="confident"`; a `raw_name` with no match is converted to
  a `target:"category"` flag with `phrase=raw_name`; the model's `ambiguity_flags` are carried
  as-is; all Mechanism-1 flags are appended (union, no dedup, no filtering); `persona_facts`
  and `payload` are copied from the state unchanged; the assembled object is set on
  `state.resolved`.
- **Inputs:** `state`, `mapping` · **Outputs:** `ResolvedRequirements` · **Failure:** none
  (bad nodes are already rejected in stage 2).

**`resolve_category_flags`**

- **Purpose:** the conditional gate plus Operation 2 orchestration.
- **What it does:** returns immediately when `state.user_responses` is empty; otherwise filters
  `state.resolved.ambiguity_flags` to `target:"category"`, pairs each with
  `user_responses[flag.phrase]`, builds the resolution instruction, executes it, and calls
  `merge_resolved_flags`.
- **Inputs:** `state` · **Outputs:** none (mutates `state.resolved`) · **Failure:**
  `CategoryResolutionError` family.

**`merge_resolved_flags`**

- **Purpose:** fold Op2 results into the existing `ResolvedRequirements` in place.
- **What it does:** for each `ResolvedFlagEntry`, exact-matches `raw_name` against
  `extracted.explicit_categories` (the raw category never left it, so the match always
  succeeds), copies characteristics, and appends a `ResolvedCategory` carrying the returned
  `provenance`; then removes every `target:"category"` flag from `ambiguity_flags`. Only
  `target:"characteristic"` flags remain; `persona_facts` and `payload` are untouched.
- **Inputs:** `state`, `result` · **Outputs:** none · **Failure:** none.

**`execute_taxonomy_mapping` / `execute_flag_resolution`**

- **Purpose:** return one schema-valid wire result or a typed failure naming the operation.
- **What it does:** iterates the bound provider order; sends the instruction as the system
  message and the categories/pairs as user content with the strict enum-constrained schema; a
  provider error moves to the next provider; the first body is validated once against the wire
  model, any violation rejects it, and the answering provider is logged.
- **Failure:** `CategoryMappingProviderError` (no provider answered),
  `CategoryMappingValidationError` (body failed the contract).

---

# 4. Manual Run Guide and Terminal Output

The runner is a dev entry point, not part of the request path in §E. It reuses the Mechanism 1
config and provider chain (`OPENAI_API_KEY`, `GROQ_API_KEY`, `LLM_PROVIDER_ORDER`, model ids)
already documented in the Mechanism 1 plan; 2A adds no new settings.

## 4.1 Running it

From `backend/`:

- First pass (Op1 only, empty `user_responses`):
  `python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run`
- Second pass (Op1 + Op2, hand-supplied responses):
  `... category_resolution_sample_run --with-responses`

Each run builds a `RequirementInterpretationState` from a fixed Mechanism-1-style extraction
(`SAMPLE_STATE`), so no re-parse is needed to exercise 2A.

## 4.2 What the runner does

It builds the responsibility through `create_requirement_interpretation(get_settings())`,
configures logging like `main.py`, then calls the 2A stage methods **in sequence** rather than
`resolve_explicit_categories`, printing a titled section after each:

| Section printed | Content |
| --- | --- |
| `INPUT STATE` | the seeded `RequirementInterpretationState` as dict; per-bucket counts |
| `OP1 - INSTRUCTION` | mapping instruction in full; taxonomy node count; few-shot count |
| `OP1 - PROVIDER ATTEMPTS` | one line per attempt: provider, model, outcome; then the raw decoded body |
| `OP1 - RESULT` | `TaxonomyMappingResult` via `model_dump_json(indent=2)` |
| `OP1 - RESOLVED` | `state.resolved` after assembly; resolved vs flag counts |
| `GATE` | whether `user_responses` is populated and whether Op2 will run |
| `OP2 - INSTRUCTION` / `OP2 - PROVIDER ATTEMPTS` / `OP2 - RESULT` | present only with `--with-responses` |
| `OP2 - RESOLVED` | `state.resolved` after merge; confirms zero `target:"category"` flags |

Stage 2/6 discard the raw body once the typed contract exists, so the runner attaches a
collecting log handler and reads the attempt lines and raw body off `DEEP_SEARCH_LOGGER_NAME`,
exactly as the Mechanism 1 runner does. On a typed failure it catches
`CategoryResolutionError`, prints the class, its `stage`, and the message, and exits non-zero.

## 4.3 Stage logging inside the service

Every 2A stage method emits one structured record under `DEEP_SEARCH_LOGGER_NAME` following the
`logger.info(json.dumps({...}))` shape already used by Mechanism 1: summaries at INFO, full
objects at DEBUG. Rejections log the reason before raising.

## 4.4 Exercising the branches by hand

| To see | Do this |
| --- | --- |
| first-pass unresolved category flag | run without `--with-responses`; a vague raw category stays a `target:"category"` flag |
| nearest-node fallback | `--with-responses` where a response is still vague; entry gets `provenance="nearest_node"` |
| confident resolution | `--with-responses` where a response is specific; entry gets `provenance="confident"` |
| match-failure handling | seed `SAMPLE_STATE` so the model can paraphrase a `raw_name`; it re-enters as a flag |
| provider switch / fallback | set `LLM_PROVIDER_ORDER=groq,openai` or invalidate `OPENAI_API_KEY` |

---

## Items settled during implementation

- **`ResolvedRequirements` location.** The spec says it "becomes part of the state" and is
  "updated in place across the two passes", so it is a field (`resolved`) on
  `RequirementInterpretationState`, not a standalone return — matching how `extracted` already
  rides the same state.
- **Provenance values.** `Literal["confident","nearest_node"]`, matching the context doc's
  `ResolvedCategory` table. Operation 1 entries are always `"confident"` because Op1 never runs
  the nearest-node fallback; the three-way "which operation" distinction the decision text
  raised is not carried, since no consumer (the router) reads it.
- **Enriched-flag ripple into Mechanism 1.** Adding required `category`/`characteristic` to
  `AmbiguityFlag` means Mechanism 1's extraction schema and the four worked-example outputs are
  updated to emit them (default `null`). This is Sub-component 1's "yes, Mechanism 1 is
  updated" decision, and it must land with the contract change or the strict schema breaks.
- **Node membership check kept despite enum.** Constrained decoding already blocks
  out-of-taxonomy nodes, but `TAXONOMY_NODE_SET` is retained as the independent second check,
  consistent with Mechanism 1 validating a body even after generation-time constraint.
- **Taxonomy as data, not an abstraction.** `amenity_taxonomy.py` is a flat node list plus a
  render helper; the Mechanism 1 note "amenity taxonomy module — out of scope, mapping is 2A"
  is what this file now fulfils.
