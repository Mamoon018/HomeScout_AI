# Deep Search — Mechanism 2 Component 2A Architecture and Modularity Decisions

Section 2 of the Mechanism 2 Component 2A plan. The file and workflow structure is in
[mechanism_2_component_2a_implementation_plan.md](mechanism_2_component_2a_implementation_plan.md).

## Baseline this fits into

- Mechanism 1 already established the responsibility class, the `StructuredLLMProvider` seam,
  the ordered provider chain, and the `create_requirement_interpretation(settings)`
  composition root — see
  [mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).
- Service contracts already live in one [feature_schemas/schemas.py](../feature_schemas/schemas.py);
  wire models are Pydantic v2 with `extra="forbid"`, in-process state is a `@dataclass`.
- Prompt text already lives apart from logic in `feature_prompts/`; the strict-schema closer
  `_apply_strict_object_rules` already exists and is reused, not rewritten.
- Before this mechanism there was **no amenity taxonomy** in `backend/`: Mechanism 1 explicitly
  deferred category-to-taxonomy mapping to Component 2A, which this file now fulfils.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** two constrained-LLM operations added as methods on the existing responsibility
  class; one always-run mapping pass and one state-gated resolution pass, both hitting the same
  injected provider chain, both constrained by a taxonomy `enum` closed at the composition root.
- **Seams (where things can change independently):**
  - LLM provider — OpenAI vs Groq, order set by `LLM_PROVIDER_ORDER` (reused from Mechanism 1).
  - Wire schema vs in-process state — providers see closed enum-constrained contracts; the
    state carries a separate mutable `ResolvedRequirements` that Op2 appends to.
  - Taxonomy as data vs the prompt/schema that reads it — nodes change in one flat list without
    touching mapping logic.
- **Component list:**
  - `UserRequirementsInterpretation` — gains the Mechanism 2 workflow and its six stages.
  - `TaxonomyMappingResult` / `FlagResolutionResult` — closed wire contracts and schema source.
  - `ResolvedCategory` / `ResolvedRequirements` — the mutable output object carried on the state.
  - `UserResponse` — one clarification answer keyed by flag phrase.
  - `amenity_taxonomy` — the maintained node list plus its render and membership helpers.
  - `StructuredLLMProvider` — reused generation contract; no new implementation.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` *(extended)* | Op1/Op2 sequencing, gate, six stages, fallback order, all-or-nothing reject | providers, wire contracts, taxonomy | — (concrete) |
| `TaxonomyMappingResult` / `MappedCategory` | Op1 output shape, closed schema, node enum | `amenity_taxonomy` | — (Pydantic model) |
| `FlagResolutionResult` / `ResolvedFlagEntry` | Op2 output shape, closed schema, node enum, provenance | `amenity_taxonomy` | — (Pydantic model) |
| `ResolvedRequirements` / `ResolvedCategory` | mutable 2A output; Op2 appends in place | `AmbiguityFlag`, `PayloadRecord` | — (dataclass) |
| `UserResponse` | one clarification answer, phrase-keyed | — | — (Pydantic model) |
| `amenity_taxonomy` | node list, render for prompt, membership set | — | — (data module) |
| `StructuredLLMProvider` | contract: schema-constrained JSON generation | — | reused (Yes: 2 providers) |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with
> its reason · `reused` = an interface introduced by an earlier mechanism, not re-abstracted.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| Taxonomy `enum` injected on `taxonomy_node` | mapping must land on a real maintained node | model invents or renames a node; downstream evaluates a scope that does not exist |
| `TAXONOMY_NODE_SET` re-check after the enum | validate-after-constrain rule carried from Mechanism 1 | a wrapped or stale body slips a non-node past generation-time constraint |
| Wire result split from mutable `ResolvedRequirements` | Op2 appends categories; strict schema forbids extra keys | Op2 cannot mutate the model's output without breaking strict mode |
| `resolved` field on the state, not a return | spec: the object is updated in place across the two passes | second pass has no shared object to append to; state loses the mapping |
| Enriched `AmbiguityFlag` fields required, default `None` | strict mode requires every property; Op2 pairs by these fields | schema breaks, or an omitted key hides which category a flag belongs to |
| `user_responses` a phrase-keyed mapping | Op2 must pair each flag with its own answer without positional guessing | responses cannot be matched to flags; the wrong answer resolves the wrong flag |
| One call per operation over all items | cross-category context must inform each mapping | per-category calls lose the shared context the spec relies on |
| Two typed exits with a `stage` attr | runner must name provider-vs-validation failure per operation | caller parses tracebacks to tell "no provider answered" from "body invalid" |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `Component2A` class / per-operation classes | rejected | locked rule; a mechanism is methods on the responsibility |
| `resolved_requirements.py` module | rejected | one `schemas.py` holds every service contract |
| `taxonomy/` package + loader/asset engine | rejected | one flat node list; no retrieval, no lookup index |
| Separate Op1 and Op2 prompt modules | rejected | both belong to Component 2A; content, not logic |
| `ResolvedRequirements` as a standalone return | rejected | spec updates it in place on the state across passes |
| Router (Category Resolution Check) node | out of scope | 2A produces the object; the branch is a later step |
| Component 2B question generation | out of scope | 2A only reads `user_responses`; 2B writes it |
| Dedup of the merged Mechanism-1 flag union | **cut** | union is intentional; no consumer needs dedup today |
| Third pass / retry / backoff layer | not added | one call per operation; invalid body is rejected outright |
| `provenance` carrying "which operation" resolved a flag | **cut** | no consumer (the router) reads it; two values suffice |
| Fuzzy/normalized `raw_name` matching for characteristics | rejected | raw category never leaves `extracted`; exact equality always matches |
| A new provider or model for 2A | rejected | reuses the Mechanism 1 chain; no new capability needed |
| Persistence of `ResolvedRequirements` | not added | handoff stays in-process and in-memory |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → TaxonomyMappingResult, FlagResolutionResult, ResolvedRequirements (contracts)
UserRequirementsInterpretation → RequirementInterpretationState (mutable; carries `resolved`)
UserRequirementsInterpretation → amenity_taxonomy (render_taxonomy, TAXONOMY_NODE_SET)
UserRequirementsInterpretation → category_resolution_instruction (prompt text, no dependencies)
schemas.py (Op1/Op2 schema builders) → amenity_taxonomy (node enum)
```

### F. Composition Root

- **Where:** unchanged — `create_requirement_interpretation(settings)` in
  [requirement_interpretation.py](../requirement_interpretation.py), which calls
  `create_llm_providers(settings)`.
- **Selects:** the same provider order (`LLM_PROVIDER_ORDER`) and model ids Mechanism 1 uses;
  2A binds no new dependency. The taxonomy `enum` is closed into the schemas at import, not at
  the root, because it is fixed data rather than a deployment choice.

### G. End-to-End Flow

1. `interpret(raw_input)` runs Mechanism 1, then calls `resolve_explicit_categories(state)`.
2. Op1 Stage 1 assembles the mapping instruction; the schema carries the taxonomy `enum`.
3. Op1 Stage 2 calls providers in order until one returns a body, validates it independently,
   and logs which provider answered.
4. Op1 Stage 3 attaches characteristics by exact `raw_name` match, converts unmatched names to
   category flags, merges Mechanism-1 flags as a union, copies persona/payload, and sets
   `state.resolved`.
5. The gate reads `state.user_responses`; on the first pass it is empty and Op2 is skipped, so
   `resolve_explicit_categories` returns the state with category flags possibly remaining.
6. When `user_responses` is present (second pass), Op2 pairs each `target:"category"` flag with
   its answer, executes one constrained call, and `merge_resolved_flags` appends the resolved
   entries and drops every category flag — mutating `state.resolved` in place.

---

## Layer 4 — Backing

- **Operations as methods, not a class:** Component 2A is two operations that share the
  responsibility's injected providers and its state, so a `Component2A` type would only hold
  methods that already have everything they need on the class — the same reasoning that kept
  Mechanism 1's stages as methods.
- **One `schemas.py` for the new contracts:** Op1, Op2, and the state all read the same
  taxonomy-mapped types, so scattering them across a `resolved_requirements.py` would force each
  operation to import a data journey from several modules.
- **Taxonomy as a flat data module:** mapping needs the node list rendered into a prompt and a
  membership set for a defensive check — both are data reads, not behavior, so a package with a
  loader would add an asset engine for a list that fits in one file.
- **Enum-constrained node plus a membership re-check:** constrained decoding shapes the node at
  generation time, but a wrapped or stale body can still carry a non-node, so `TAXONOMY_NODE_SET`
  is the same independent second check Mechanism 1 applies after strict output.
- **Wire result separate from the mutable output:** `extra="forbid"` blocks post-hoc fields and
  Op2 must append categories, so the object Op2 mutates cannot be the strict wire model — it is
  the dataclass `ResolvedRequirements`, mirroring the wire-vs-state split from Mechanism 1.
- **`resolved` on the state:** the spec says the object is built once and updated in place across
  the two passes, so a standalone return would give the second pass nothing to append to; a field
  on the same mutable state is what lets Op2 read and extend Op1's work.
- **Required enriched-flag fields with `None` defaults:** strict mode requires every property, and
  making `category`/`characteristic` required means an empty value arrives as `null` rather than
  an omitted key — the same "no defaults on wire fields" rule Mechanism 1 relies on.
- **Phrase-keyed `user_responses`:** Op2 must attach the right answer to the right flag without
  positional coupling, so keying the mapping by the flag's own `phrase` is what removes the guess;
  a list would reintroduce positional matching between two independently ordered collections.
- **Programmatic characteristic attachment:** the raw category and its characteristics never left
  `extracted`, so the model only needs to return `raw_name` + `taxonomy_node`; copying
  characteristics by exact equality keeps the customer's stated traits authoritative rather than
  asking the model to echo and possibly alter them.
- **Union of Mechanism-1 flags, no dedup:** every flag from Mechanism 1 must survive into 2A's
  output for later components, and no consumer needs a deduplicated set today, so a filter would
  drop data with no reader — cut for the same reason Mechanism 1 cut unused carriers.
- **Fallback on transport failure only:** an out-of-contract mapping body is a contract violation,
  not an availability problem, so retrying on another provider would mask it; the operation rejects
  the whole body, exactly as Mechanism 1 does.
- **Two typed exits per operation:** the runner and any caller must tell "no provider answered"
  from "body failed the contract" without reading a traceback, so `CategoryMappingProviderError`
  and `CategoryMappingValidationError` carry a `stage`, matching Mechanism 1's error surface.
- **Prompt text in its own module:** the mapping and resolution rules plus worked pairs are a large
  natural-language block; keeping them in `category_resolution_instruction.py` keeps the stage
  methods readable, the one file Mechanism 1 also kept apart.
- **Runner calls stages one at a time:** `resolve_explicit_categories` returns only the final
  state, so the runner drives the six stages in sequence to print every intermediate object and
  reads the discarded raw body off `DEEP_SEARCH_LOGGER_NAME`, the same technique the Mechanism 1
  runner uses.
