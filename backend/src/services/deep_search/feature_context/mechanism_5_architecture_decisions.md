# Deep Search — Mechanism 5 Architecture and Modularity Decisions

Section 2 of the Mechanism 5 plan. The file and workflow structure is in
[mechanism_5_implementation_plan.md](mechanism_5_implementation_plan.md).

## Baseline this fits into

- Mechanism 1 established the responsibility class, the `StructuredLLMProvider` seam, the
  ordered provider chain, and `create_requirement_interpretation(settings)` — see
  [mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).
- Mechanism 2 added `state.resolved`, `_call_providers` with `provider_error_cls`, and
  taxonomy data — see
  [mechanism_2_component_2a_architecture_decisions.md](mechanism_2_component_2a_architecture_decisions.md)
  and
  [mechanism_2_router_and_2b_architecture_decisions.md](mechanism_2_router_and_2b_architecture_decisions.md).
- Mechanism 4 added `state.inferred_categories`, `InferredCategory`, and sequenced
  `interpret` after Mechanism 2 — see
  [mechanism_4_architecture_decisions.md](mechanism_4_architecture_decisions.md).
- Service contracts already live in one [feature_schemas/schemas.py](../feature_schemas/schemas.py);
  wire models are Pydantic v2 with `extra="forbid"`; in-process state is a `@dataclass`.
- Prompt text already lives apart from logic in `feature_prompts/`; `_apply_strict_object_rules`
  already exists and is reused, not rewritten.
- Before this slice, `interpret` ran parse, Mechanism 2, then Mechanism 4 and returned.
  `depth` did not exist on `ResolvedCategory` or `InferredCategory`.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** methods on the existing responsibility class; one constrained generation on
  the reused provider chain; a closed wire body is validated, then `depth` is stamped onto
  existing category objects.
- **Seams (where things can change independently):**
  - LLM provider — OpenAI vs Groq, order set by `LLM_PROVIDER_ORDER` (reused from Mechanism 1).
  - Wire `DepthAssignmentResult` vs store field — providers see `{category_id, depth}`; code
    writes `depth` onto `ResolvedCategory` / `InferredCategory`.
  - Depth prompt text vs stage methods — scale, floors, and the metric contract change without
    touching execute/stamp.
- **Component list:**
  - `UserRequirementsInterpretation` — gains the Mechanism 5 workflow and three stage methods.
  - `DepthAssignmentEntry` / `DepthAssignmentResult` — closed wire contract and schema source.
  - `DepthLevel` plus `depth` on `ResolvedCategory` and `InferredCategory`.
  - `DepthAssignmentError` family — provider vs validation exits with `stage`.
  - `depth_assignment_instruction` — task, scale, floors, triggers, contract, six pairs.
  - `StructuredLLMProvider` — reused generation contract; no new implementation.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` *(extended)* | M5 workflow, execute, stamp | providers, wire contracts, prompt module | — (concrete) |
| `DepthAssignmentResult` / `DepthAssignmentEntry` | wire shape, closed schema, depth enum | `DepthLevel` | — (Pydantic model) |
| `ResolvedCategory` / `InferredCategory` *(extended)* | store `depth`, default `None` | `DepthLevel` | — (dataclass) |
| `DepthAssignmentError` family | provider vs validation exits with `stage` | — | — (exceptions) |
| `depth_assignment_instruction` | M5 prompt text and `build_*` | schema dict | — (content module) |
| `StructuredLLMProvider` | contract: schema-constrained JSON generation | — | reused (Yes: 2 providers) |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with
> its reason · `reused` = an interface introduced by an earlier mechanism, not re-abstracted.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| Wire `DepthAssignmentResult` split from store stamp | model must not rewrite node, chars, or reasoning | schema would invite those fields or omit id echo |
| Two typed depth exits with a `stage` attr | caller must name provider-vs-validation without a traceback | inference or mapping errors mislabel a depth failure |
| Prompt text in `depth_assignment_instruction.py` | scale, floors, acceptance, and metric contract are this component's rules | inference file owns depth policy |
| Reuse `_call_providers` with `DepthAssignmentProviderError` | ordered OpenAI-then-Groq chain is already injected | fallback loop copied, or an inference error raised |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `DepthCalibrationService` / `Mechanism5` class | rejected | locked rule; stages share the responsibility's providers |
| Per-`taxonomy_node` depth table | rejected | assignment is dynamic LLM judgement from origin plus trigger |
| `depth_contracts.py` module | rejected | one `schemas.py` holds every service contract |
| New LLM provider or model for M5 | rejected | reuses the Mechanism 1 chain; no new capability needed |
| Retry / backoff layer | not added | schema, id, or floor miss rejects the whole body |
| Clamp / fill missing ids with the origin floor | rejected | locked all-or-nothing; code must not invent a depth |
| Metric objects or rationale on the category | rejected | this component does not emit metrics |
| Generalize `_clarification_coverage_miss` | rejected | helper is clarification-labeled; depth uses a local check |
| `DeepSearchFeature` coordinator class | not added | only Responsibility 1 exists; `interpret` sequences M5 |
| Persistence of `depth` | not added | handoff stays in-process and in-memory |
| Mix inferred entries into `resolved_explicit_categories` | rejected | explicit priority is field separation |
| `asyncio.gather` inside M5 | rejected | one call; stages are data-dependent |
| Re-call M1–M4 in the M5 sample runner | rejected | earlier mechanisms already sampled; seed after M4 |
| `DepthAssignmentInput` record for Operation 1 | rejected | instruction function plus render helper, as in M4 |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → DepthAssignmentResult (wire)
UserRequirementsInterpretation → RequirementInterpretationState (mutates depth on existing entries)
UserRequirementsInterpretation → depth_assignment_instruction (prompt text, no dependencies)
schemas.py (schema builder) → DepthAssignmentResult, DepthLevel
```

### F. Composition Root

- **Where:** unchanged — `create_requirement_interpretation(settings)` in
  [requirement_interpretation.py](../requirement_interpretation.py), which calls
  `create_llm_providers(settings)`.
- **Selects:** the same provider order (`LLM_PROVIDER_ORDER`) and model ids Mechanisms 1, 2,
  and 4 use. Mechanism 5 binds no new dependency. The depth schema is closed at import, not
  at the root, because it is a fixed contract rather than a deployment choice.

### G. End-to-End Flow

1. `interpret(raw_input)` runs Mechanism 1, then `run_explicit_category_resolution(state)`,
   then `run_persona_driven_category_inference(state)`.
2. `run_per_category_depth_calibration(state)` runs next. If both category lists are empty,
   return the state. No model call.
3. Otherwise assemble the depth instruction (scale inlined; user content is not inside it).
4. Execute calls providers in bound order, validates independently, checks id coverage and
   the explicit floor, and returns `DepthAssignmentResult`.
5. Stamp writes `depth` onto matching `ResolvedCategory` / `InferredCategory` rows by
   `category_id`. Other fields stay unchanged.
6. `interpret` returns the state. Mechanism 3 and Mechanism 6 are not called.

---

## Layer 4 — Backing

- **Methods, not a class:** Mechanism 5 shares the injected providers and the mutable state
  Mechanisms 1–4 already own. A new type would only hold methods that already have
  everything they need on the responsibility.
- **`interpret` sequences M5 after M4:** locked constraint. Mechanism 3 is out of scope and
  is not read by this call.
- **Skip is a workflow branch, not a second entry point:** the spec names one skip at the
  component boundary when both lists are empty. A separate skip method would duplicate the
  branch the workflow already owns.
- **Wire vs stamp:** `extra="forbid"` blocks extra keys. Identity already exists on the
  entries. Code writes `depth` after accept, the same reason M4 stamps `category_id` after
  strip. The model must not rewrite `taxonomy_node`, `characteristics`, or `reasoning`.
- **`_call_providers` reused, 2B coverage helper not:** the fallback loop is shared behavior
  with a stated second error class. Id coverage is a local helper so clarification log
  events do not fire on a depth miss.
- **Origin is labeled in user content:** the model does not infer origin from the node name.
  A missing label would let an inferred node be treated as explicit, or the reverse.
- **Tools and the metric contract stay in the instruction:** the model needs to know what
  the bands authorize. This component does not fetch and does not emit metric objects.
- **`StructuredLLMProvider` not re-abstracted:** two providers are already bound at the
  composition root. Mechanism 5 does not add a third implementation or a different
  generation capability.
- **No `gather` inside M5:** one constrained call; instruction, execute, and stamp are
  data-dependent. Independent I/O to overlap does not exist in this component.
