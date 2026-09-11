# Deep Search — Mechanism 2 Router and Component 2B Architecture and Modularity Decisions

Section 2 of the Mechanism 2 Router and Component 2B plan. The file and workflow structure
is in
[mechanism_2_router_and_2b_implementation_plan.md](mechanism_2_router_and_2b_implementation_plan.md).

## Baseline this fits into

- Mechanism 1 established the responsibility class, the `StructuredLLMProvider` seam, the
  ordered provider chain, and `create_requirement_interpretation(settings)` — see
  [mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).
- Component 2A added taxonomy mapping, `state.resolved`, `user_responses` keyed by
  `category_id`, and `_call_providers` — see
  [mechanism_2_component_2a_architecture_decisions.md](mechanism_2_component_2a_architecture_decisions.md).
- Service contracts already live in one [feature_schemas/schemas.py](../feature_schemas/schemas.py);
  wire models are Pydantic v2 with `extra="forbid"`; in-process state is a `@dataclass`.
- Prompt text already lives apart from logic in `feature_prompts/`; `_apply_strict_object_rules`
  already exists and is reused, not rewritten.
- Before this slice, `interpret` ran parse then 2A pass 1 only. The router, 2B, and the
  two-pass loop had no invoker. `category_resolution_passes` did not exist on the state.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** a loop method on the existing responsibility class; 2A is reused; the router is
  a counter-plus-branch; 2B is one constrained generation plus blocking CLI persist, hitting
  the same injected provider chain.
- **Seams (where things can change independently):**
  - LLM provider — OpenAI vs Groq, order set by `LLM_PROVIDER_ORDER` (reused from Mechanism 1).
  - Wire `ClarificationResult` vs in-process `user_responses` — providers see a closed
    contract; the state carries answers 2A Operation 2 reads.
  - 2B prompt text vs stage methods — rules and few-shots change without touching the loop.
- **Component list:**
  - `UserRequirementsInterpretation` — gains the Mechanism 2 loop, the router, and 2B stages.
  - `ClarificationQuestion` / `ClarificationResult` — closed wire contract and schema source.
  - `CategoryResolutionRoute` — `"component_2b"` or `"mechanism_3"`.
  - `UserResponse` — one CLI answer keyed by `category_id` (already on the state).
  - `clarification_instruction` — 2B task, rules, negative rules, two worked pairs.
  - `StructuredLLMProvider` — reused generation contract; no new implementation.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` *(extended)* | Mechanism 2 loop, router, 2B stages, coverage retry | providers, wire contracts, prompt module | — (concrete) |
| `ClarificationResult` / `ClarificationQuestion` | 2B output shape, closed schema, 5 options + `"other"` | — | — (Pydantic model) |
| `CategoryResolutionRoute` | binary inspect destination | — | — (Literal alias) |
| `RequirementInterpretationState` *(extended)* | pass counter; `user_responses` 2B writes | `UserResponse`, `ResolvedRequirements` | — (dataclass) |
| `ClarificationError` family | provider vs validation exits with `stage` | — | — (exceptions) |
| `clarification_instruction` | 2B prompt text and `build_*` | schema dict | — (content module) |
| `StructuredLLMProvider` | contract: schema-constrained JSON generation | — | reused (Yes: 2 providers) |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with
> its reason · `reused` = an interface introduced by an earlier mechanism, not re-abstracted.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| Wire `ClarificationResult` split from `user_responses` | 2B must persist answers; strict schema forbids extra keys | CLI has no typed body; provider output would be mutated |
| Two typed 2B exits with a `stage` attr | caller must name provider-vs-validation for generation | traceback parsing; 2A mapping errors mislabel a 2B failure |
| Prompt text in `clarification_instruction.py` | 2B has its own rules and two few-shots | 2A mapping file owns 2B copy, or the class buries the prompt |
| `provider_error_cls` on `_call_providers` | reuse the chain; 2B must raise `ClarificationProviderError` | copy the fallback loop, or 2B raises 2A's mapping error |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `Router` class | rejected | not a component; one inspect, no second implementation |
| `Component2B` class | rejected | locked rule; stages share the responsibility's providers |
| `DeepSearchFeature` coordinator class | not added | only Responsibility 1 exists; `interpret` returns the state |
| CLI port / `PromptAdapter` | rejected | one stdin channel; tests monkeypatch `input` |
| `clarification_contracts.py` module | rejected | one `schemas.py` holds every service contract |
| Merge 2B prompt into 2A's instruction file | rejected | 2A owns mapping/resolution; 2B rules change independently |
| Retry / backoff layer | not added | one inline second call on coverage failure only |
| New LLM provider or model for 2B | rejected | reuses the Mechanism 1 chain; no new capability needed |
| Taxonomy inlined in the 2B prompt | **cut** | 2B asks what the category maps to; it does not select a node |
| Mechanism 3 invoked from this loop | rejected | locked: state is returned to the coordinator |
| Persistence of `user_responses` | not added | handoff stays in-process and in-memory |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → ClarificationResult, ClarificationQuestion, CategoryResolutionRoute (contracts)
UserRequirementsInterpretation → RequirementInterpretationState (mutable; carries passes and user_responses)
UserRequirementsInterpretation → clarification_instruction (prompt text, no dependencies)
schemas.py (2B schema builder) → ClarificationResult (closed schema, no taxonomy enum)
```

### F. Composition Root

- **Where:** unchanged — `create_requirement_interpretation(settings)` in
  [requirement_interpretation.py](../requirement_interpretation.py), which calls
  `create_llm_providers(settings)`.
- **Selects:** the same provider order (`LLM_PROVIDER_ORDER`) and model ids Mechanism 1 and
  2A use. 2B binds no new dependency. The clarification schema is closed at import, not at
  the root, because it is a fixed contract rather than a deployment choice.

### G. End-to-End Flow

1. `interpret(raw_input)` runs Mechanism 1, then `run_explicit_category_resolution(state)`.
2. 2A pass 1 runs Operation 1 and skips Operation 2 (`user_responses` empty).
3. The router increments `category_resolution_passes` and emits `component_2b` or
   `mechanism_3`.
4. On `mechanism_3`, `interpret` returns the state. Mechanism 3 is not called.
5. On `component_2b`, Stage 1 assembles the clarification instruction (no taxonomy).
6. Stage 2 calls providers in order, validates independently, retries once on coverage
   failure, and returns `ClarificationResult`.
7. Stage 3 prints numbered options, reads stdin, and writes `user_responses[category_id]`.
   `resolved.*` is unchanged.
8. 2A pass 2 calls `resolve_category_flags` only (Operation 1 is not re-run).
9. The router inspects again (`passes` becomes 2), emits `mechanism_3`, and `interpret`
   returns.

---

## Layer 4 — Backing

- **Loop as a method, not a class:** Mechanism 2 is 2A plus a branch plus 2B, all sharing
  the injected providers and one mutable state. A `Mechanism2` or `Component2B` type would
  only hold methods that already have everything they need on the responsibility — the same
  reasoning that kept Mechanism 1 and 2A as methods.
- **Router as a method returning a Literal:** the spec says this is not a component (no LLM
  call, no output object). A `Router` type would have one function and no second
  implementation. The workflow needs an inspectable destination for tests, so the method
  returns `"component_2b"` or `"mechanism_3"` and mutates only `category_resolution_passes`.
- **Increment first, then cap:** the router owns the counter and must not route to 2B when
  `passes >= 2`. Incrementing before the flag check makes the hard cap structural: a leftover
  category flag after pass 2 cannot re-enter 2B.
- **Pass 2 calls `resolve_category_flags`, not `resolve_explicit_categories`:** Operation 1
  rebuilds `state.resolved`. The spec requires pass 2 to reuse that object and skip Op1.
  Calling the existing Op2 method is the structural skip; a new pass-mode flag on 2A is not
  required.
- **`interpret` returns the state:** Mechanism 3 is out of scope and there is no feature
  class yet. Returning after the second inspect is the locked handoff to the next mechanism.
- **One `schemas.py` for the new contracts:** 2B's wire types, the pass counter, and
  `user_responses` all ride the same state 2A already extends, so a `clarification_contracts.py`
  would split one data journey across modules.
- **2B prompt in its own module:** 2A's file owns mapping and flag-resolution rules. 2B's
  task is taxonomy-scope questions with no node list. Putting both in one file would mix two
  components' natural-language blocks, which is the split Mechanism 1 already made between
  extraction and 2A.
- **Wire result separate from `user_responses`:** `extra="forbid"` blocks post-hoc fields,
  and the CLI must attach a customer `response` the model did not generate. The object 2B
  mutates cannot be the strict wire model — it is `state.user_responses`, mirroring 2A's
  wire-vs-state split.
- **`provider_error_cls` on `_call_providers`:** 2B must reuse the ordered chain and must
  raise `ClarificationProviderError`, not `CategoryMappingProviderError`. A defaulted
  parameter keeps 2A's call sites unchanged and avoids copying the fallback loop. It is not
  a new abstraction.
- **Coverage retry inline, not a retry layer:** schema failure is a contract violation and
  is rejected immediately, matching Mechanism 1 and 2A. Coverage can omit, duplicate, or
  invent a `category_id` on an otherwise valid body; the stated requirement is one repeat of
  the same instruction and schema. A backoff/retry type would own a policy that does not
  exist.
- **CLI as `input` / `print`:** one blocking stdin channel is the stated collect path. An
  adapter would exist for a second implementation that is not required. Tests replace
  `input` at the builtin; no production seam is needed.
- **No taxonomy in the 2B prompt:** 2B clarifies what the stated category maps to; it does
  not select a node. Inlining the 128-node list would ask the model to do 2A's job.
- **Two typed 2B exits with `stage`:** the caller must tell "no provider answered" from
  "body failed schema or coverage" without a traceback, and must not reuse 2A's mapping
  errors. `execute_clarification_questions` is the stage name, matching 2A's method-name
  `stage` values.
- **`StructuredLLMProvider` not re-abstracted:** two providers are already bound at the
  composition root. 2B does not add a third implementation or a different generation
  capability.
