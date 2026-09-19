# Deep Search: Mechanism 6 Architecture and Modularity Decisions

Section 2 of the Mechanism 6 plan. File and workflow structure is in
[mechanism_6_implementation_plan.md](mechanism_6_implementation_plan.md).

## Baseline this fits into

- Mechanism 1 established the responsibility class, the `StructuredLLMProvider` seam, the ordered provider chain, and `create_requirement_interpretation(settings)`.
- Mechanism 2 added `state.resolved`, `_call_providers` with `provider_error_cls`, and taxonomy data.
- Mechanism 4 added `state.inferred_categories` and `InferredCategory`.
- Mechanism 5 added `depth` on both category types, `_depth_id_coverage_miss`, and the depth scale text that Mechanism 6 depends on.
- Service contracts already live in one `feature_schemas/schemas.py`. Wire models are Pydantic v2 with `extra="forbid"`. In-process state is a `@dataclass`.
- The whole call chain is already async down to the HTTP client.
- Before this slice, `interpret` returned after Mechanism 5 and no metric object existed.

## Layer 1. Glance

### A. Architecture at a Glance

- **Shape:** methods on the existing responsibility class. One constrained generation on the reused provider chain. A closed wire body is validated, filtered metric by metric, and written into a new state list.
- **Seams (where things can change independently):**
  - LLM provider: OpenAI vs Groq, order set by `LLM_PROVIDER_ORDER` (reused).
  - Wire body vs stored object: providers see `{category_id, metrics}`. Code writes `CategoryMetricSet` with a copied `taxonomy_node`.
  - Metric prompt text vs stage methods: bands, tie rules, and worked pairs change without touching execute, filter, or write.
- **Component list:**
  - `UserRequirementsInterpretation`: gains the Mechanism 6 workflow and six stage methods.
  - `MetricEntry` / `CategoryMetricsEntry` / `MetricDefinitionResult`: closed wire contract and schema source.
  - `MetricSpec` / `CategoryMetricSet` and `state.category_metrics`: stored result.
  - `FIXED_DIMENSIONS_BY_DEPTH`: one constant, read by the prompt and later stages.
  - `MetricDefinitionError` family: provider vs validation exits with `stage`.
  - `metric_definition_instruction`: task, bands, contract, rules, worked pairs.
  - `StructuredLLMProvider`: reused generation contract. No new implementation.

## Layer 2. Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` *(extended)* | M6 workflow, execute, filter, shortfall, write | providers, wire contracts, prompt module | — (concrete) |
| `MetricDefinitionResult` and nested wire models | wire shape, closed schema, closed enums | value aliases | — (Pydantic model) |
| `MetricSpec`, `CategoryMetricSet` | stored metrics and per-category set | value aliases | — (dataclass) |
| `FIXED_DIMENSIONS_BY_DEPTH` | fixed dimensions by depth | `DepthLevel` | — (constant) |
| `MetricDefinitionError` family | provider vs validation exits with `stage` | — | — (exceptions) |
| `metric_definition_instruction` | M6 prompt text and `build_*` | schema dict, fixed-dimension constant | — (content module) |
| `StructuredLLMProvider` | contract: schema-constrained JSON generation | — | reused (Yes: 2 providers) |

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| Wire models split from stored dataclasses | model must not emit `taxonomy_node` or edit categories | schema would invite fields code owns |
| Separate `state.category_metrics` list | locked: category objects stay unchanged | metrics have no stated home; M5 objects would be edited |
| `metrics: None` vs `[]` on the set | `basic_profile` (no dynamic metrics) differs from "nothing survived" | later stages cannot tell not-eligible from all-rejected |
| Two typed exits with `stage` | caller must tell provider from validation failure | depth or inference errors mislabel a metric failure |
| Prompt text in its own module | bands, tie rules, and worked pairs are this component's rules | depth prompt file owns metric policy |
| Reuse `_call_providers` with `MetricDefinitionProviderError` | provider chain is already injected | fallback loop copied, or a depth error raised |
| Fixed-dimension constant in `schemas.py` | prompt "do not propose" list and later stages need one source | two copies drift; model restates fixed fields |
| Rule checks in code, not schema | Groq strict mode has no `minLength`, `maxItems`, or conditionals; K3 needs state | blank text and over-cap lists reach retrieval |
| Drop-only filter with logged rejections | locked: one bad metric must not discard the rest | a single blank field rejects every category |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `MetricDefinitionService` class | rejected | locked rule; stages share the providers and state |
| Rule interface with one class per K rule | rejected | six checks on one dataclass; one consumer |
| `metric_contracts.py` or `metric_rules.py` module | rejected | one `schemas.py`; rules live beside the filter method |
| Per-`taxonomy_node` or per-group metric catalog | rejected | locked: LLM defines metrics each run |
| Store fixed dimensions on each category | rejected | locked: constant looked up by depth |
| Facts list beside metrics | rejected | locked: a fact is a contract-passing metric |
| Rejection-record dataclass | not added | read only by the log and the runner |
| Persist rejected metrics on the state | not added | locked: logged, not stored |
| Retry or repair of a failing metric | rejected | locked: no fill, rewrite, or clamp |
| Retry / backoff layer | not added | schema or id miss rejects the whole body |
| Generalize `_depth_id_coverage_miss` or rename it | reused as-is | signature is already generic; rename would edit Mechanism 5 |
| `DeepSearchFeature` coordinator class | not added | only Responsibility 1 exists; `interpret` sequences M6 |
| `asyncio.gather` inside M6 | rejected | one call; stages are data-dependent |
| New provider, model, or setting for M6 | rejected | reuses the Mechanism 1 chain |
| Re-call M1 to M5 in the sample runner | rejected | earlier mechanisms are already sampled; seed after M5 |

## Layer 3. Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → MetricDefinitionResult (wire)
UserRequirementsInterpretation → RequirementInterpretationState (writes category_metrics; reads depth)
UserRequirementsInterpretation → metric_definition_instruction (prompt text)
metric_definition_instruction → FIXED_DIMENSIONS_BY_DEPTH, MAX_METRICS_PER_BAND (schemas.py)
schemas.py (schema builder) → MetricDefinitionResult, value aliases
```

### F. Composition Root

- **Where:** unchanged: `create_requirement_interpretation(settings)` in `requirement_interpretation.py`, which calls `create_llm_providers(settings)`.
- **Selects:** the same provider order (`LLM_PROVIDER_ORDER`) and model ids as Mechanisms 1, 2, 4, and 5. Mechanism 6 binds no new dependency. The metric schema is closed at import because it is a fixed contract, not a deployment choice.

### G. End-to-End Flow

1. `interpret(raw_input)` runs Mechanism 1, Mechanism 2, Mechanism 4, then Mechanism 5.
2. `run_per_category_metric_definition(state)` runs next. No categories: return with `category_metrics` empty. No eligible category: write `None` sets and return. No model call in either case.
3. Otherwise assemble the metric instruction. User content carries only eligible rows.
4. Execute calls providers in bound order, validates the body against the schema, and checks the id set.
5. `apply_metric_contract` drops metrics failing K1 to K6 and logs each drop.
6. `report_metric_shortfalls` logs categories left without a required band.
7. `write_category_metrics` assigns `state.category_metrics`. `interpret` returns the state. Mechanism 3 and Mechanism 7 are not called.

## Layer 4. Backing

- **Methods, not a class:** Mechanism 6 shares the providers and the mutable state Mechanisms 1 to 5 already own. A new type would hold methods that already have everything they need on the responsibility.
- **Separate `category_metrics` list:** the result needs an owner. Stamping onto the category objects was rejected by the spec. `category_id` is the join key, and `taxonomy_node` is copied so later stages need not look it up.
- **`None` vs `[]`:** a `basic_profile` category has no dynamic metrics by definition. An eligible category with no survivors is a shortfall. The two states need different values.
- **Rules in code:** Groq strict mode supports types, required keys, closed objects, and enums. It does not support length, count, or conditional keywords. The OpenAI documentation page reviewed for this plan did not list its unsupported keywords, so the schema is written to the smaller set. K3 also needs the category's `depth`, which the schema cannot see.
- **Drop-only filter beside a whole-body reject:** a malformed body means the model did not follow the contract shape, so nothing in it is trusted. A well-formed body with one rule-breaking metric is mostly usable. The spec locks both behaviors.
- **Shortfall as a log report:** with drop-only rejection, a minimum cannot be enforced. The report keeps the gap visible to the log and to the runner.
- **`_call_providers` and `_depth_id_coverage_miss` reused:** the fallback loop and the id check are shared behavior with a stated second error class.
- **Origin and depth labeled in user content:** the model must not infer either from the node name. A missing depth label would let a metric band exceed the assigned depth without a cue.
- **Fixed dimensions as a constant:** the model needs the list to avoid restating it. Later stages need the same list to know what is fetched without metrics. One owner prevents two copies.
- **`StructuredLLMProvider` not re-abstracted:** two providers are already bound at the composition root. Mechanism 6 adds no third implementation and no different generation capability.
- **No `gather`:** one constrained call. Instruction, execute, filter, and write are data-dependent. There is no independent I/O to overlap.
