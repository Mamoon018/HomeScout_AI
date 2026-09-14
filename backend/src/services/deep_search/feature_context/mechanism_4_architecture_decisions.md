# Deep Search — Mechanism 4 Architecture and Modularity Decisions

Section 2 of the Mechanism 4 plan. The file and workflow structure is in
[mechanism_4_implementation_plan.md](mechanism_4_implementation_plan.md).

## Baseline this fits into

- Mechanism 1 established the responsibility class, the `StructuredLLMProvider` seam, the
  ordered provider chain, and `create_requirement_interpretation(settings)` — see
  [mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).
- Mechanism 2 added `state.resolved`, `_call_providers` with `provider_error_cls`, and
  taxonomy data (`AMENITY_TAXONOMY_NODES`, `TAXONOMY_NODE_SET`, `render_taxonomy`) — see
  [mechanism_2_component_2a_architecture_decisions.md](mechanism_2_component_2a_architecture_decisions.md)
  and
  [mechanism_2_router_and_2b_architecture_decisions.md](mechanism_2_router_and_2b_architecture_decisions.md).
- Service contracts already live in one [feature_schemas/schemas.py](../feature_schemas/schemas.py);
  wire models are Pydantic v2 with `extra="forbid"`; in-process state is a `@dataclass`.
- Prompt text already lives apart from logic in `feature_prompts/`; `_apply_strict_object_rules`
  and `_inject_taxonomy_node_enum` already exist and are reused, not rewritten.
- Before this slice, `interpret` ran parse then Mechanism 2 and returned.
  `inferred_categories` did not exist on the state.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** methods on the existing responsibility class; one constrained generation on
  the reused provider chain; a closed wire body is validated, then stripped and stamped onto
  a new state field.
- **Seams (where things can change independently):**
  - LLM provider — OpenAI vs Groq, order set by `LLM_PROVIDER_ORDER` (reused from Mechanism 1).
  - Wire `InferredCategoriesResult` vs store `InferredCategory` — providers see
    `taxonomy_node` + `reasoning`; code stamps `category_id` after strip.
  - Inference prompt text vs stage methods — distinctness and evidence rules change without
    touching execute/strip.
- **Component list:**
  - `UserRequirementsInterpretation` — gains the Mechanism 4 workflow and three stage methods.
  - `InferredCategoryEntry` / `InferredCategoriesResult` — closed wire contract and schema source.
  - `InferredCategory` — stored entry (`taxonomy_node`, `category_id`, `reasoning`).
  - `RequirementInterpretationState` — new `inferred_categories` list, default `[]`.
  - `InferenceError` family — provider vs validation exits with `stage`.
  - `inference_instruction` — task, distinctness, evidence, negation, six pairs.
  - `StructuredLLMProvider` — reused generation contract; no new implementation.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` *(extended)* | M4 workflow, execute, strip/write | providers, wire contracts, prompt module | — (concrete) |
| `InferredCategoriesResult` / `InferredCategoryEntry` | wire shape, `maxItems: 2`, closed schema | — | — (Pydantic model) |
| `InferredCategory` | stored identity after strip | — | — (dataclass) |
| `RequirementInterpretationState` *(extended)* | `inferred_categories` default `[]` | `InferredCategory` | — (dataclass) |
| `InferenceError` family | provider vs validation exits with `stage` | — | — (exceptions) |
| `inference_instruction` | M4 prompt text and `build_*` | schema dict, `render_taxonomy` | — (content module) |
| `StructuredLLMProvider` | contract: schema-constrained JSON generation | — | reused (Yes: 2 providers) |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with
> its reason · `reused` = an interface introduced by an earlier mechanism, not re-abstracted.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| Wire `InferredCategoriesResult` split from store `InferredCategory` | model must not emit `category_id`; store forbids `ResolvedCategory` fields | provider schema would require `category_id` or leak `raw_name` |
| Two typed inference exits with a `stage` attr | caller must name provider-vs-validation without a traceback | mapping or clarification errors mislabel an inference failure |
| Prompt text in `inference_instruction.py` | distinctness, evidence, and negation are this component's rules | 2A mapping file owns inference copy |
| Reuse `_call_providers` with `InferenceProviderError` | ordered OpenAI-then-Groq chain is already injected | fallback loop copied, or 2A mapping error raised |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `InferenceService` / `Mechanism4` class | rejected | locked rule; stages share the responsibility's providers |
| Distinctness clamp in code | rejected | spec: aliases and Step 2 are instruction-only |
| `inference_contracts.py` module | rejected | one `schemas.py` holds every service contract |
| New LLM provider or model for M4 | rejected | reuses the Mechanism 1 chain; no new capability needed |
| Retry / backoff layer | not added | schema miss or unknown node rejects the whole body |
| `DeepSearchFeature` coordinator class | not added | only Responsibility 1 exists; `interpret` sequences M4 |
| Generalize `_assert_nodes_in_taxonomy` | rejected | helper logs 2A events and raises 2A errors |
| Generalize provider-attempt log event names | not this slice | `_call_providers` still emits `category_resolution.*`; 2B already accepted that |
| Persistence of `inferred_categories` | not added | handoff stays in-process and in-memory |
| Mix inferred entries into `resolved_explicit_categories` | rejected | explicit priority is field separation |
| Re-call M1/M2 in the M4 sample runner | rejected | earlier mechanisms already sampled; seed after M2 |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → InferredCategoriesResult, InferredCategory (contracts)
UserRequirementsInterpretation → RequirementInterpretationState (mutable; inferred_categories)
UserRequirementsInterpretation → inference_instruction (prompt text, no dependencies)
schemas.py (schema builder) → InferredCategoriesResult, AMENITY_TAXONOMY_NODES (enum)
```

### F. Composition Root

- **Where:** unchanged — `create_requirement_interpretation(settings)` in
  [requirement_interpretation.py](../requirement_interpretation.py), which calls
  `create_llm_providers(settings)`.
- **Selects:** the same provider order (`LLM_PROVIDER_ORDER`) and model ids Mechanism 1 and
  2 use. Mechanism 4 binds no new dependency. The inference schema is closed at import, not
  at the root, because it is a fixed contract rather than a deployment choice.

### G. End-to-End Flow

1. `interpret(raw_input)` runs Mechanism 1, then `run_explicit_category_resolution(state)`.
2. `run_persona_driven_category_inference(state)` always runs next. There is no skip branch.
3. Stage 2 assembles the inference instruction (taxonomy inlined; user content is not inside it).
4. Stage 3 calls providers in bound order, validates independently, checks `TAXONOMY_NODE_SET`,
   and returns `InferredCategoriesResult`.
5. Stage 4 strips exact-node duplicates, stamps `category_id`, and writes
   `state.inferred_categories`.
6. `interpret` returns the state. Mechanism 3 and Mechanism 5 are not called.

---

## Layer 4 — Backing

- **Methods, not a class:** Mechanism 4 shares the injected providers and the mutable state
  Mechanisms 1 and 2 already own. A new type would only hold methods that already have
  everything they need on the responsibility.
- **`interpret` sequences M4 after M2:** locked constraint. Mechanism 3 is out of scope and
  is not read by this call. Inserting M3 later does not change M4's inputs (`persona_facts`,
  resolved nodes + characteristics, payload, taxonomy).
- **Wire vs store:** `extra="forbid"` blocks post-hoc `category_id`. Identity is assigned
  after strip, same reason extraction keeps `category_id` off the provider schema. Store is
  a dataclass like `ResolvedCategory` because code writes it, not the model.
- **`_call_providers` reused, `_assert_nodes_in_taxonomy` not:** the fallback loop is shared
  behavior with a stated second error class. The taxonomy helper is 2A-labeled logging plus
  `CategoryMappingValidationError`. An inline set-membership check avoids turning that helper
  into a generic validator.
- **No skip when `persona_facts` is empty:** empty list is a valid body the instruction must
  produce. A code skip would hide whether the call returned `[]`.
- **Strip never raises:** failing the request on collision would discard a valid sibling.
  Empty list after a full strip is success.
- **Cap is schema failure, not truncation:** truncating would accept an over-long body and
  hide a contract miss.
- **Ids from `extracted.explicit_categories`:** spec. Numbering from
  `resolved_explicit_categories` only would reuse an unmapped extracted id.
- **`StructuredLLMProvider` not re-abstracted:** two providers are already bound at the
  composition root. Mechanism 4 does not add a third implementation or a different
  generation capability.
