# Deep Search — Async Conversion Architecture and Modularity Decisions

Section 2 of the async conversion plan. The file and workflow structure is in
[async_conversion_implementation_plan.md](async_conversion_implementation_plan.md).

## Baseline this fits into

- Mechanism 1 established the responsibility class, the `StructuredLLMProvider` seam, the
  ordered provider chain, and `create_requirement_interpretation(settings)` — see
  [mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).
- Mechanism 2 added `state.resolved`, `_call_providers` with `provider_error_cls`, the
  router, and 2B coverage retry — see
  [mechanism_2_component_2a_architecture_decisions.md](mechanism_2_component_2a_architecture_decisions.md)
  and
  [mechanism_2_router_and_2b_architecture_decisions.md](mechanism_2_router_and_2b_architecture_decisions.md).
- Mechanism 4 added `state.inferred_categories` and rewired `interpret` after Mechanism 2
  — see [mechanism_4_architecture_decisions.md](mechanism_4_architecture_decisions.md).
- Service contracts already live in one [feature_schemas/schemas.py](../feature_schemas/schemas.py).
  Prompt text already lives in `feature_prompts/`. Exception modules already exist.
- Before this slice, `generate_structured` was a blocking SDK call. `openai==3.10.0`
  already ships `AsyncOpenAI`. `groq==1.7.0` already ships `AsyncGroq`.
  `pytest-asyncio` is already in [backend/pytest.ini](../../../../../pytest.ini) with
  `asyncio_mode = auto`.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** the same concrete responsibility class behind the same `StructuredLLMProvider`
  protocol. Only the I/O contract becomes async. Adapters still chosen at the existing
  composition root.
- **Seams (where things can change independently):**
  - LLM provider — OpenAI vs Groq, order still `LLM_PROVIDER_ORDER`.
  - Sync CPU / CLI vs async I/O — instruction, validate, merge, inspect, and `input()`
    stay sync; HTTP generation is awaited.
  - Client lifetime — construct in the sync factory; close with `aclose` at the end of a
    run.
- **Component list:**
  - `UserRequirementsInterpretation` — sequences mechanisms; awaits I/O stages; closes
    providers.
  - `StructuredLLMProvider` — one async schema-constrained generation plus `aclose`.
  - `OpenAIStructuredProvider` / `GroqStructuredProvider` — async SDK adapters.
  - `RequirementInterpretationState` — mutable handoff, mutated only in sequential stages.
  - Three sample runners — asyncio entry for live checks.
  - `FakeStructuredProvider` — recorded async bodies for tests.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` | sequencing, fallback order, reject-on-invalid, `aclose` | providers, wire contracts | — (concrete) |
| `StructuredLLMProvider` | async `generate_structured` and `aclose` | — | Yes: 2 providers, switchable order |
| `OpenAIStructuredProvider` | `AsyncOpenAI` call, auth, decode, close | `StructuredLLMProvider` | implements |
| `GroqStructuredProvider` | `AsyncGroq` call, auth, decode, close | `StructuredLLMProvider` | implements |
| `RequirementInterpretationState` | mutable handoff; sequential writes | wire contracts | — (dataclass) |
| `create_requirement_interpretation` / `create_llm_providers` | sync composition root | settings, adapter factories | — (function) |
| Sample runners / fakes | live and dummy callers | responsibility | — (not request-path) |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with
> its reason · `implements` = an implementation of an interface.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| One coordinated conversion of the implemented chain | `generate_structured` is shared by M1, M2, M4 | mixed protocol leaves 2/4 with unawaited coroutines |
| Keep `StructuredLLMProvider`; no second async protocol | two providers already forced this seam | every caller splits across sync and async contracts |
| Sequential await for provider fallback | Groq may run only after OpenAI fails | `gather` starts both and ignores that dependency |
| Sequential await for Mechanism 1 → 2 → 4 | each workflow reads fields the previous wrote | overlapping stages race on the same state object |
| Add `aclose` on the protocol | async SDK clients hold an HTTP session | unclosed sessions leak after a sample or a request |
| Factory stays sync | construction is not the I/O wait | every test setup needs an event loop for no HTTP call |
| `input()` stays blocking and sync | clarification CLI is sample-only | wrapping stdin now wraps a path FastAPI will not use |
| `langdetect` stays on the event-loop thread | short CPU on bounded intake text | a worker is scheduled for a non-I/O wait |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `DeepSearchFeature` coordinator | not added | one responsibility exists |
| Class per mechanism or async wrapper types | rejected | stages remain methods |
| Unify `execute_and_validate` onto `_call_providers` | not this conversion | log event names and error types differ |
| `gather` of OpenAI and Groq | rejected | fallback is data-dependent |
| Convert Places / add a Places async protocol | rejected | no Deep Search consumer yet |
| FastAPI Deep Search route | not implemented | out of this slice |
| `asyncio.to_thread` for `langdetect` or `input()` | rejected | short CPU; CLI is sample-only |
| New fourth sample runner | rejected | convert the three existing runners |
| Sync `generate_structured` wrapper that calls `asyncio.run` | rejected | cannot nest inside FastAPI’s loop later |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → RequirementInterpretationState (mutable; sequential writes)
sample runners / tests → UserRequirementsInterpretation
```

### F. Composition Root

- **Where:** `create_requirement_interpretation(settings)` in
  [requirement_interpretation.py](../requirement_interpretation.py), which still calls
  `create_llm_providers(settings)` in
  [llm_provider.py](../../../clients/llm_provider.py).
- **Selects:** ordered `AsyncOpenAI` / `AsyncGroq` adapters from `LLM_PROVIDER_ORDER`.
  Still a sync function.
- **Closes:** callers await `UserRequirementsInterpretation.aclose()`, which awaits each
  provider `aclose`.

### G. End-to-End Flow

1. Caller (`asyncio.run` in a sample, later a FastAPI route) awaits `interpret(raw_input)`
   or a stage method.
2. Mechanism 1: sync intake and instruction, await `execute_and_validate`, sync handoff.
3. Mechanism 2: await mapping (and maybe clarification generation and flag resolution);
   inspect and assemble stay sync; CLI collect stays blocking sync.
4. Mechanism 4: sync instruction, await inference execute, sync strip/write.
5. Each execute stage awaits `_call_providers` or the Mechanism 1 fallback loop.
6. The funnel awaits `generate_structured` on the first provider; on `LLMProviderError` it
   awaits the next.
7. The adapter awaits `chat.completions.create` on the async SDK client, then decodes JSON
   on the event-loop thread.
8. Caller awaits `aclose`.

---

## Layer 4 — Backing

- **Async on the protocol, not a second interface:** the existing seam is the I/O
  boundary; only its execution mode changes. A parallel sync protocol would split every
  caller of Mechanisms 1, 2, and 4.
- **Sync factory plus async `aclose`:** construction vs teardown are different
  operations; only teardown waits on the HTTP session. Making the factory async would
  force every test setup through an event loop for no HTTP call.
- **Sequential await everywhere in Responsibility 1:** every I/O group either needs the
  previous result or is a failure-triggered fallback. `gather` of providers would start
  Groq before OpenAI has failed. `gather` of mechanisms would race writes on the same
  `RequirementInterpretationState`.
- **Blocking CLI `input()` left in place:** it is not on the future request path;
  replacing it belongs to an HTTP clarification mechanism, not this conversion.
- **`langdetect` left on the event-loop thread:** intake text is already bounded by the
  word-count gate. The call is short CPU, not an I/O wait.
- **`execute_and_validate` keeps its own loop:** Mechanism 1 logs
  `PROVIDER_ATTEMPT_EVENT` / `RAW_BODY_EVENT` and raises extraction errors.
  `_call_providers` logs `category_resolution.*` events and takes a
  `provider_error_cls`. Unifying them would change log names and error types that
  runners and callers already depend on.
- **Coverage retry stays a second sequential await:** the retry uses the same
  instruction and user content, but it is data-dependent on the first body’s ids. Overlap
  would start a second call before coverage is known.
- **`resolve_explicit_categories` and `resolve_category_flags` become async:** they call
  execute stages even though they also contain sync gate/assemble work. An awaited
  operation must be async down its chain.
- **Inspect-only tests stay sync:** `inspect_category_resolution` does not touch HTTP.
  Forcing those tests through an event loop would await a method that is not a coroutine.
