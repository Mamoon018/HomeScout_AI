# Deep Search — Async Conversion Implementation Plan

Convert the implemented **User Requirement Interpretation** stack so every awaited I/O
call is async down to the HTTP client. Mechanism 1 → 2 → 4 stays sequential. Provider
fallback stays sequential. This is a behavior-preserving conversion of the already
implemented chain. Domain contracts, prompts, and Google Places stay out of this change.

Architecture and modularity decisions live in
[async_conversion_architecture_decisions.md](async_conversion_architecture_decisions.md).

Locked decisions: `generate_structured` is async on the existing protocol; factories stay
sync constructors; `aclose` is added on the protocol, both adapters, and the
responsibility; Mechanism 1 `execute_and_validate` keeps its own awaited fallback loop;
coverage retry is a second sequential await; `input()` and `langdetect` stay on the
event-loop thread; inspect-only tests stay sync; the three existing sample runners are
converted in place.

## Explicitly out of scope

- Google Places client and
  [backend/src/services/google_places_sample_run.py](../../../google_places_sample_run.py)
- FastAPI route wiring for Deep Search
- Unimplemented mechanisms (3, 5–9) and later responsibilities
- Unifying Mechanism 1 `execute_and_validate` onto `_call_providers`
- `asyncio.gather` / `create_task` for providers or mechanisms
- A new fourth sample-runner file
- Schema, prompt, taxonomy, or exception-module redesign
- Offloading `langdetect` or CLI `input()` to a worker
- New dependencies (`openai==3.10.0` already ships `AsyncOpenAI`; `groq==1.7.0` already
  ships `AsyncGroq`; `pytest-asyncio` is already in
  [backend/pytest.ini](../../../../../pytest.ini) with `asyncio_mode = auto`)

---

# 1. File and Module Structure

No new runtime modules. Same files, changed contracts. Placement follows the live
layering: SDK adapters in `clients/`, workflow in `requirement_interpretation.py`, tests
in `backend/tests/`, live runners in `feature_sample_runs/`.

### New files — this slice adds 2 canonical docs

| File | Owns | Contains |
| --- | --- | --- |
| [async_conversion_implementation_plan.md](async_conversion_implementation_plan.md) | this plan | file map, blueprint, async structure, runners |
| [async_conversion_architecture_decisions.md](async_conversion_architecture_decisions.md) | Section 2 | glance, justifications, wiring, backing |

### Modified files — I/O adapters

| File | Change |
| --- | --- |
| [backend/src/clients/llm_provider.py](../../../clients/llm_provider.py) | async `generate_structured`; `AsyncOpenAI` / `AsyncGroq`; add `aclose`; factories stay sync |

### Modified files — responsibility

| File | Change |
| --- | --- |
| [requirement_interpretation.py](../requirement_interpretation.py) | I/O-touching methods and workflows become async; add `aclose`; CPU/CLI methods stay sync |

### Modified files — live runners (existing files, not a new runner)

| File | Change |
| --- | --- |
| [requirement_interpretation_sample_run.py](../feature_sample_runs/requirement_interpretation_sample_run.py) | `run_sample_extraction` async; `asyncio.run` in `main`; `finally` awaits `aclose` |
| [category_resolution_sample_run.py](../feature_sample_runs/category_resolution_sample_run.py) | `run_sample_resolution` async; `asyncio.run` in `main`; `finally` awaits `aclose` |
| [category_inference_sample_run.py](../feature_sample_runs/category_inference_sample_run.py) | `run_sample_inference` async; `asyncio.run` in `main`; `finally` awaits `aclose` |

Each `run_sample_*` becomes async. Stage print order and seeded inputs stay the same.

### Modified files — dummy-provider tests

| File | Change |
| --- | --- |
| [test_mechanism_2_clarification.py](../../../../../tests/services/deep_search/test_mechanism_2_clarification.py) | async fake; I/O tests `await`; inspect-only tests stay sync |
| [test_mechanism_4_inference.py](../../../../../tests/services/deep_search/test_mechanism_4_inference.py) | async fake; I/O tests `await` |

`FakeStructuredProvider.generate_structured` becomes async. `aclose` is a no-op.

### Unchanged

| File / area | Why it stays |
| --- | --- |
| schemas, prompts, taxonomy, exception modules | conversion does not add fields or error types |
| config, logging | no new settings or log event names |
| Places client, FastAPI `main.py` | no Deep Search consumer yet |
| `create_requirement_interpretation` location | composition root stays a sync factory |

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| Second async protocol beside the sync one | same `StructuredLLMProvider`, async methods | mixed protocol leaves 2/4 with unawaited coroutines |
| Unify `execute_and_validate` onto `_call_providers` | keep both loops, both awaited | log event names and error types differ |
| `gather` of OpenAI and Groq | sequential await | Groq may run only after OpenAI fails |
| `gather` of Mechanism 1 → 2 → 4 | sequential await | each workflow reads fields the previous wrote |
| Async factory | sync constructors | construction is not the I/O wait |
| `asyncio.to_thread` for `langdetect` or `input()` | stay on the event-loop thread | short CPU; CLI is sample-only |
| New fourth sample runner | convert the three existing runners | seeded inputs and print sections already exist |
| Sync wrapper that calls `asyncio.run` inside generate | rejected | cannot nest inside FastAPI’s loop later |

---

# 2. Architecture and Modularity Decisions

See [async_conversion_architecture_decisions.md](async_conversion_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation — raw input → per-category specification
   ├─ interpret — sequential await of M1, M2, M4
   ├─ Mechanism 1: parse_unstructured_input
   │    ├─ intake_and_assemble_payload — sync
   │    ├─ build_extraction_instruction — sync
   │    ├─ execute_and_validate — await providers, then sync validate
   │    └─ assemble_handoff — sync
   ├─ Mechanism 2: run_explicit_category_resolution
   │    ├─ resolve_explicit_categories — await Op1, maybe await Op2
   │    ├─ inspect_category_resolution — sync
   │    ├─ clarify_unmapped_categories — await generate, sync collect
   │    └─ resolve_category_flags — maybe await Op2
   ├─ Mechanism 4: run_persona_driven_category_inference
   │    ├─ build_inference_instruction — sync
   │    ├─ execute_category_inference — await providers, then sync validate
   │    └─ write_inferred_categories — sync
   └─ aclose — await each provider close
```

The schema is a **contract** (§B). Sample runners and the fixture set are **not** in the
request path (§E). There is no `DeepSearchFeature` node because only Responsibility 1
exists.

## B. Data Contracts

Unchanged objects. Conversion does not add fields. All of these already live in
[feature_schemas/schemas.py](../feature_schemas/schemas.py), except the error types in
[exceptions/deep_search.py](../../../exceptions/deep_search.py) and
[exceptions/llm.py](../../../exceptions/llm.py).

| Contract | Purpose | Fields | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `PayloadRecord` | bounded input | `normalized_text: str` · `raw_text: str` | immutable | Stage 1 → later stages |
| `ExtractedRequirements` | four buckets | `explicit_categories` · `ambiguity_flags` · `persona_facts` | wire model | Mechanism 1 → 2/4 |
| `RequirementInterpretationState` | mutable handoff | `payload`, `extracted`, `resolved`, `user_responses`, `inferred_categories`, pass count | **mutable** — sequential writes only | M1 → M2 → M4 |
| `TaxonomyMappingResult` | Op1 wire body | mapped nodes + unmapped ids | wire model | Op1 execute → assemble |
| `ClarificationResult` | 2B wire body | questions keyed by category_id | wire model | 2B execute → collect |
| `FlagResolutionResult` | Op2 wire body | nodes for previously unmapped ids | wire model | Op2 execute → merge |
| `InferredCategoriesResult` | M4 wire body | zero to two `{taxonomy_node, reasoning}` | wire model | M4 execute → write |
| `LLMProviderError` / service typed errors | same exits as today | message · `stage` on service errors | immutable | execute stages → caller |

Rules surfaced here: empty bucket = `[]` not omitted; closed schema; the state object is
mutable because Mechanisms 2 and 4 accumulate on the same handoff; `aclose` is teardown
after the return, not a field on the data object.

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol | `name`, `model`; `async generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict [raises: LLMProviderError]`; `async aclose() -> None` | `OpenAIStructuredProvider`, `GroqStructuredProvider`; tests: `FakeStructuredProvider` | execute stages, `_call_providers` |
| `create_openai_provider` / `create_groq_provider` / `create_llm_providers` | sync factories | `(settings: Settings) -> provider or tuple` | one each | `create_requirement_interpretation` |
| `create_requirement_interpretation` | sync composition root | `(settings: Settings) -> UserRequirementsInterpretation` | one | sample runners |

Factories stay sync. Why the protocol stays one interface lives in the architecture file.

## D. Class and Method Blueprint

**`StructuredLLMProvider` / adapters** in
[llm_provider.py](../../../clients/llm_provider.py).

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `generate_structured` | `async (*, instruction: str, user_content: str, json_schema: dict, schema_name: str) -> dict [raises: LLMProviderError]` | one awaited schema-constrained HTTP call, then decode |
| `aclose` | `async () -> None` | close the SDK HTTP session |
| `create_openai_provider` | `(settings: Settings) -> OpenAIStructuredProvider` | sync constructor for `AsyncOpenAI` |
| `create_groq_provider` | `(settings: Settings) -> GroqStructuredProvider` | sync constructor for `AsyncGroq` |
| `create_llm_providers` | `(settings: Settings) -> tuple[StructuredLLMProvider, ...]` | bind adapters in `LLM_PROVIDER_ORDER` |

**`UserRequirementsInterpretation`** in
[requirement_interpretation.py](../requirement_interpretation.py). The class holds the
same injected provider chain.

Become async (await I/O, then existing sync work):

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `interpret` | `async (raw_input: str) -> RequirementInterpretationState` | sequential await of M1, M2, M4 |
| `parse_unstructured_input` | `async (raw_input: str) -> RequirementInterpretationState` | intake, instruction, await execute, assemble |
| `execute_and_validate` | `async (payload: PayloadRecord, instruction: str) -> ExtractedRequirements [raises: ExtractionProviderError, ExtractionValidationError]` | await providers, then sync validate |
| `run_explicit_category_resolution` | `async (state) -> RequirementInterpretationState [mutates: state]` | await 2A, maybe await 2B and pass 2 |
| `clarify_unmapped_categories` | `async (state) -> None [mutates: state.user_responses]` | await generate, then sync collect |
| `execute_clarification_questions` | `async (state, instruction) -> ClarificationResult` | await call, maybe one coverage retry |
| `resolve_explicit_categories` | `async (state) -> RequirementInterpretationState [mutates: state.resolved]` | await Op1, maybe await Op2 |
| `execute_taxonomy_mapping` | `async (state, instruction) -> TaxonomyMappingResult` | await providers, then sync validate |
| `resolve_category_flags` | `async (state) -> None [mutates: state.resolved]` | maybe await Op2 after the gate |
| `execute_flag_resolution` | `async (pairs, instruction) -> FlagResolutionResult` | await providers, then sync validate |
| `run_persona_driven_category_inference` | `async (state) -> RequirementInterpretationState [mutates: state.inferred_categories]` | sync instruction, await execute, sync write |
| `execute_category_inference` | `async (state, instruction) -> InferredCategoriesResult` | await providers, then sync validate |
| `_call_providers` | `async (...) -> tuple[dict, str]` | sequential await of bound providers |
| `aclose` | `async () -> None` | await each provider `aclose` |

Stay sync (same signatures as today):

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `intake_and_assemble_payload` | `(raw_input: str) -> PayloadRecord` | bound and normalize input |
| `build_extraction_instruction` | `(json_schema: dict) -> str` | assemble extraction prompt |
| `assemble_handoff` | `(payload, extracted) -> RequirementInterpretationState` | wrap validated IR as mutable handoff |
| `inspect_category_resolution` | `(state) -> CategoryResolutionRoute` | increment pass count, emit route |
| `build_clarification_questions_instruction` | `(json_schema: dict) -> str` | assemble 2B prompt |
| `collect_clarification_responses` | `(state, result) -> None [mutates: state.user_responses]` | blocking CLI collect |
| `_validate_clarification_schema` | `(body, *, provider) -> ClarificationResult` | independent schema check |
| `build_taxonomy_mapping_instruction` | `(json_schema: dict) -> str` | assemble Op1 prompt |
| `assemble_resolved_requirements` | `(state, mapping) -> ResolvedRequirements [mutates: state.resolved]` | attach names, flag unmapped ids |
| `build_flag_resolution_instruction` | `(json_schema: dict) -> str` | assemble Op2 prompt |
| `merge_resolved_flags` | `(state, result) -> None [mutates: state.resolved]` | append nodes, drop category flags |
| `build_inference_instruction` | `(json_schema: dict) -> str` | assemble M4 prompt |
| `write_inferred_categories` | `(state, body) -> None [mutates: state.inferred_categories]` | strip, stamp, write list |
| `_assert_nodes_in_taxonomy` / `_assert_mapping_covers_extracted` / `_assert_resolution_covers_pairs` | existing signatures | independent second checks |
| `is_english` | `(text: str) -> bool` | language gate |
| `_prompt_clarification_option` / `_prompt_other_description` | existing signatures | blocking stdin |
| `create_requirement_interpretation` | `(settings: Settings) -> UserRequirementsInterpretation` | sync composition root |

## E. Runtime Flow — Data Object Journey

Request path is unchanged except awaits at I/O. Test harness and sample printing are not
in this path.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `intake_and_assemble_payload` (sync) | raw str | `PayloadRecord` | `{normalized_text, raw_text}` |
| 2 | `execute_and_validate` (await) | payload, instruction | `ExtractedRequirements` or typed error | four buckets |
| 3 | `assemble_handoff` (sync) | payload, extracted | `RequirementInterpretationState` | mutable handoff |
| 4 | `execute_taxonomy_mapping` (await) | extracted | mapping body | categories mapped / unmapped ids |
| 5 | `assemble_resolved_requirements` (sync) | mapping | `state.resolved` | explicit nodes + flags |
| 6 | `inspect_category_resolution` (sync) | resolved, pass count | route | `component_2b` or `mechanism_3` |
| 7 | `execute_clarification_questions` (await, maybe second await) | flags | `ClarificationResult` | questions |
| 8 | `collect_clarification_responses` (sync, blocking input) | questions | `state.user_responses` | answers keyed by category_id |
| 9 | `execute_flag_resolution` (await) | flag/response pairs | `FlagResolutionResult` | nodes for previously unmapped ids |
| 10 | `execute_category_inference` (await) | resolved + persona | `InferredCategoriesResult` | inferred list on wire |
| 11 | `write_inferred_categories` (sync) | body, explicit nodes | `state.inferred_categories` | stripped, stamped ids |

**Transformation trace (shape only):**

```
str
 → PayloadRecord
 → ExtractedRequirements
 → RequirementInterpretationState
 → (+ resolved)
 → (+ user_responses, maybe)
 → (+ inferred_categories)
```

**Approach at the real decision points:**

- Provider order is bound at the composition root. Try the first provider, await it, and
  await the next only on `LLMProviderError`.
- Clarification coverage miss triggers one more sequential `_call_providers` await with
  the same instruction and user content. A second miss raises `ClarificationValidationError`.
- Router after pass 1: category flags → 2B; otherwise return for Mechanism 4. After pass 2,
  always Mechanism 4.
- Validation after each awaited body stays all-or-nothing and sync.
- `aclose` is not on the data object; it is teardown after the return.

## F. Method Detail

**`generate_structured` (both adapters)**

- **Purpose:** one awaited schema-constrained completion, decoded to a dict.
- **What it does:** await `chat.completions.create` with the same messages and
  `response_format` as today; map the same SDK exceptions to `LLMProviderError`; decode
  JSON on the event-loop thread after the await.
- **Inputs:** instruction, user_content, json_schema, schema_name · **Outputs:** dict ·
  **Failure:** `LLMProviderError`, `LLMResponseTruncatedError`.

**`_call_providers`**

- **Purpose:** try bound providers in order until one body returns.
- **What it does:** await `generate_structured` per provider; on `LLMProviderError` log
  failed and continue; on success log answered and return `(body, provider.name)`; if none
  answered, raise `provider_error_cls`. Do not schedule the next provider until the current
  await finishes.
- **Inputs:** instruction, user content, schema, stage, error class · **Outputs:**
  `(dict, str)` · **Failure:** `provider_error_cls`. Shared-state: none. Local `body` /
  `answered_by` only.

**`execute_and_validate`**

- **Purpose:** Mechanism 1’s fallback loop plus independent validation.
- **What it does:** same loop as today with `await generate_structured`; keep
  `PROVIDER_ATTEMPT_EVENT` / `RAW_BODY_EVENT`; then sync `model_validate` and
  `_stamp_category_identities`. Do not call `_call_providers`.
- **Inputs:** payload, instruction · **Outputs:** `ExtractedRequirements` · **Failure:**
  `ExtractionProviderError`, `ExtractionValidationError`.

**`execute_clarification_questions`**

- **Purpose:** one constrained call, schema then coverage, one coverage retry.
- **What it does:** await `_call_providers`; sync schema validate; if coverage miss, await
  `_call_providers` again; second miss raises. The retry is data-dependent on the first
  body’s ids.
- **Inputs:** state, instruction · **Outputs:** `ClarificationResult` · **Failure:**
  `ClarificationProviderError`, `ClarificationValidationError`.

**`collect_clarification_responses`**

- **Purpose:** blocking CLI collect into `state.user_responses`.
- **What it does:** unchanged `input()` loop. Called from async
  `clarify_unmapped_categories` as a sync call. Occupies the event-loop thread while
  waiting for stdin. Allowed because this method is sample/CLI-only.
- **Inputs:** state, clarification result · **Outputs:** none · **Failure:** none.

**`aclose` (responsibility and adapters)**

- **Purpose:** close async HTTP sessions after a run.
- **What it does:** adapters await `client.close()`; responsibility awaits each provider;
  fakes return immediately.
- **Inputs:** none · **Outputs:** none · **Failure:** none.

**`interpret` / mechanism workflows**

- **Purpose:** preserve M1 → M2 → M4 ordering.
- **What it does:** await each I/O-touching child; call sync children without await. Do
  not overlap mechanisms.
- **Inputs:** raw input or state · **Outputs:** `RequirementInterpretationState` ·
  **Failure:** typed errors from the awaited execute stages.

---

# G. Async Structure Map

Each layer is classified by data dependency, then marked sequential await, concurrent, or
offloaded. No layer in this conversion has independent I/O that can overlap. Concurrency
(`gather` of amenity category searches) belongs to a later Places responsibility.

**Layer 1 — Responsibility entry (`interpret`)**

| Field | Value |
| --- | --- |
| Operations / I/O | `parse_unstructured_input`, `run_explicit_category_resolution`, `run_persona_driven_category_inference`. No direct HTTP. Each child awaits LLM inside. |
| Data dependency | data-dependent. M2 needs `extracted`. M4 needs `resolved`. |
| Execution mode | sequential await. Pattern: await M1 → await M2 → await M4. |
| Shared-state | one `RequirementInterpretationState`. Sequential writes. Not concurrent. |
| Blocking check | none at this layer. |

**Layer 2 — Mechanism 1 workflow**

| Field | Value |
| --- | --- |
| Operations / I/O | sync intake, sync instruction, await `execute_and_validate`, sync assemble. I/O is the provider HTTP call. |
| Data dependency | data-dependent. Execute needs payload and instruction. |
| Execution mode | sequential await at execute only. |
| Shared-state | not concurrent. |
| Blocking check | `langdetect` in intake is sync CPU on short text. Stays on the event-loop thread. |

**Layer 3 — Mechanism 2 workflow**

| Field | Value |
| --- | --- |
| Operations / I/O | await taxonomy mapping; sync inspect; maybe await clarification generate; sync CLI collect; maybe await flag resolution. |
| Data dependency | data-dependent. Router needs `resolved`. 2B needs category flags. Op2 needs `user_responses`. |
| Execution mode | sequential await. Coverage retry is a second sequential await inside execute. |
| Shared-state | one state object. `resolved` and `user_responses` written in order. Not concurrent. |
| Blocking check | `input()` in collect is blocking stdin. Leave on the event-loop thread. CLI-only. |

**Layer 4 — Mechanism 4 workflow**

| Field | Value |
| --- | --- |
| Operations / I/O | sync instruction, await execute, sync write. |
| Data dependency | data-dependent. Write needs the validated body and explicit nodes. |
| Execution mode | sequential await. |
| Shared-state | writes `inferred_categories` after execute returns. Not concurrent. |
| Blocking check | none beyond the awaited HTTP call. |

**Layer 5 — Provider funnel**

| Field | Value |
| --- | --- |
| Operations / I/O | await `generate_structured` per provider in bound order. |
| Data dependency | data-dependent. Next provider runs only after the previous await fails. |
| Execution mode | sequential await. Do not `gather` providers. |
| Shared-state | not concurrent. |
| Blocking check | none after adapters are async. |

**Layer 6 — SDK adapters**

| Field | Value |
| --- | --- |
| Operations / I/O | await `chat.completions.create`. JSON decode after the await. |
| Data dependency | one call at a time from the funnel. |
| Execution mode | sequential await of one HTTP call. |
| Shared-state | none. |
| Blocking check | decode and log are short CPU on the event-loop thread. Close path is `aclose`, also awaited. |

**Layer 7 — Callers**

| Field | Value |
| --- | --- |
| Operations / I/O | samples await stage methods and `aclose`. Tests await I/O methods. Inspect tests stay sync. |
| Data dependency | same stage order as today. |
| Execution mode | `asyncio.run` at sample `main`. Pytest asyncio mode auto for async tests. |
| Shared-state | not concurrent. |
| Blocking check | live Mechanism 2 sample still blocks on stdin when 2B runs without `--with-responses`. |

---

# 4. Sample Runners and Dummy-Provider Fixture Set

Neither check is part of the request path in §E. No new settings. No new sample-runner
file.

## 4.1 Live sample runners (convert in place)

From `backend/`:

| Command | What it exercises |
| --- | --- |
| `python -m src.services.deep_search.feature_sample_runs.requirement_interpretation_sample_run` | Mechanism 1 stages against one real LLM call |
| `python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run` | Mechanism 2 loop, live 2B CLI |
| `python -m src.services.deep_search.feature_sample_runs.category_resolution_sample_run --with-responses` | Mechanism 2 with seeded answers, no CLI |
| `python -m src.services.deep_search.feature_sample_runs.category_inference_sample_run` | Mechanism 4 against one real LLM call |

Seeded inputs, titled sections, log-based attempt/raw-body prints, and “do not re-call
earlier mechanisms” rules stay as they are. `run_sample_*` becomes async. `main` becomes
`asyncio.run(...)`. `finally` awaits `aclose`. Nothing written to disk.

## 4.2 Dummy-provider fixture set

Same two pytest modules. `FakeStructuredProvider.generate_structured` becomes `async` and
still returns recorded dicts. `aclose` is a no-op. Tests that call
`clarify_unmapped_categories`, `execute_clarification_questions`, `resolve_category_flags`,
or `run_persona_driven_category_inference` become async and await. Tests that only call
`inspect_category_resolution` stay sync.

From `backend/`:

`pytest tests/services/deep_search`

Verification after code change: `pytest backend/tests/services/deep_search` then the four
live commands above. Contracts, fallback order, validation errors, and log events must
match today’s behavior.
