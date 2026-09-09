# Deep Search — Mechanism 1 Architecture and Modularity Decisions

Section 2 of the Mechanism 1 plan. The file and workflow structure is in
[mechanism_1_implementation_plan.md](mechanism_1_implementation_plan.md).

## Baseline this fits into

- Config is `pydantic-settings` with env aliases and an `@lru_cache get_settings()` in
  [backend/src/core/config.py](../../core/config.py).
- External integrations are a `create_x_client(settings) -> XClient` factory **in the same
  module as the client class**, which maps SDK errors to a local exception tree — see
  [backend/src/clients/google_places.py](../../clients/google_places.py) and
  [backend/src/exceptions/places.py](../../exceptions/places.py).
- Pydantic is v2.13.4; in-process types are `@dataclass(frozen=True)` + `Enum` (see
  [backend/src/services/auth/access_token.py](../auth/access_token.py)).
- Before this mechanism there was **no LLM code, no prompt asset, and no amenity taxonomy**
  in `backend/`; `services/deep_search/` held only the context markdown.

---

## Layer 1 — Glance

### A. Architecture at a Glance

- **Shape:** one concrete responsibility class whose methods are the mechanism workflow and
  its stages, calling a single LLM capability protocol whose implementations are ordered and
  injected at a factory composition root.
- **Seams (where things can change independently):**
  - LLM provider — OpenAI vs Groq, order set by `LLM_PROVIDER_ORDER`.
  - Wire schema vs in-process state — the provider sees a closed Pydantic contract;
    downstream mechanisms mutate a separate dataclass.
- **Component list:**
  - `UserRequirementsInterpretation` — responsibility entry; owns the mechanism 1 workflow
    and its stages.
  - `ExtractedRequirements` — closed four-bucket wire contract and provider schema source.
  - `RequirementInterpretationState` — mutable handoff object carrying the payload and the
    buckets.
  - `StructuredLLMProvider` — contract for one schema-constrained generation.
  - `OpenAIStructuredProvider` / `GroqStructuredProvider` — SDK adapters.
  - `is_english` — local pre-call language gate.

---

## Layer 2 — Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `UserRequirementsInterpretation` | mechanism sequencing, stages 1/3/4/5, fallback order, all-or-nothing reject | providers, wire contract | — (concrete) |
| `ExtractedRequirements` | bucket separation, closed schema, empty-as-`[]` | — | — (Pydantic model) |
| `RequirementInterpretationState` | mutable handoff; carries payload text for 2A | `ExtractedRequirements`, `PayloadRecord` | — (dataclass) |
| `StructuredLLMProvider` | contract: schema-constrained JSON generation | — | Yes: 2 providers, switchable order |
| `OpenAIStructuredProvider` | OpenAI SDK, auth, strict schema, error mapping | `StructuredLLMProvider` | implements |
| `GroqStructuredProvider` | Groq SDK, auth, strict schema, error mapping | `StructuredLLMProvider` | implements |
| `is_english` | language classification | `langdetect` | — (function, called directly) |

> `Abstracted?` legend: `—` = concrete class/function · `Yes: <trigger>` = interface with
> its reason · `implements` = an implementation of an interface.

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| `StructuredLLMProvider` protocol | OpenAI primary and Groq fallback, both stated | responsibility binds one SDK; second provider needs service edits |
| Ordered provider tuple injected | primary/fallback must be switchable | provider order hard-coded inside the stage method |
| `model` beside `name` on the protocol | stage 4 log line must name the model | stage reaches into an SDK client to log what it was told to log |
| Wire contract split from mutable state | 2A appends to the handoff; strict schema forbids extra keys | later mechanisms cannot attach results without breaking strict mode |
| State carries `PayloadRecord` | 2A and 3A resolve using the customer's own wording | downstream mechanisms lose the text they reason over |
| Two exception modules, client and service | provider failure and validation failure are distinct exits | caller cannot tell "no provider answered" from "response invalid" |
| `stage` class attribute on the service errors | the runner must report which stage exited | runner parses tracebacks to name the failing stage |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| `DeepSearchFeature` coordinator class | not added | only one responsibility exists; nothing to coordinate |
| Class per stage | rejected | locked rule; stages are methods |
| Class per mechanism workflow | rejected | mechanism is a method that sequences stage methods |
| One file per mechanism | rejected | mechanisms 2–9 extend the same class in the same file |
| One file per data contract | rejected | one `schemas.py` holds the service's contracts |
| `clients/llm/` package | rejected | one client module matches `google_places.py` |
| `utils/` layer for `is_english` | rejected | single consumer; lives beside the intake stage |
| Injected `language_detector` parameter | **cut** | its only trigger was the removed test tier |
| `ValidatedExtraction` wrapper | **cut** | existed to carry the removed raw response |
| `ExtractionArtifacts` run record | **cut** | required only by the removed Sub-component 6 |
| `provider_name` on a contract | **cut** | no consumer left; logged at call time instead |
| `min_word_count` constructor parameter | **cut** | one value, no second caller; module constant instead |
| `word_count` on `PayloadRecord` | **cut** | intake checks the bound and does not republish it |
| `FallbackLLMProvider` composite | rejected | ordered tuple plus one loop already satisfies switching |
| Retry / backoff layer | not added | no retry requirement stated; invalid response is rejected outright |
| Prompt-template engine or asset loader | not added | one instruction, one schema; module constants suffice |
| Persistence of the parsed object | not added | handoff is explicitly in-process and in-memory |
| Interface for `UserRequirementsInterpretation` | kept concrete | one implementation, no second consumer stated |
| Amenity taxonomy module | out of scope | mapping is Component 2A; locked out here |
| `print()` inside stage methods | rejected | service logs via `DEEP_SEARCH_LOGGER_NAME`; the runner prints |
| Skipping a keyless provider in the factory | rejected | both keys are configured; a named provider that cannot be built is an error |
| Sample run script | **added** | stated requirement: run the mechanism against a real call and read every stage |

---

## Layer 3 — Wiring

### E. Dependency Direction

```
UserRequirementsInterpretation → [StructuredLLMProvider]  ← OpenAIStructuredProvider, GroqStructuredProvider
UserRequirementsInterpretation → ExtractedRequirements, PayloadRecord, RequirementInterpretationState (contracts)
UserRequirementsInterpretation → extraction_instruction (prompt text, no dependencies)
UserRequirementsInterpretation → is_english (module function)
```

### F. Composition Root

- **Where:** `create_requirement_interpretation(settings)` in
  [requirement_interpretation.py](requirement_interpretation.py), which calls
  `create_llm_providers(settings)` in [clients/llm_provider.py](../../clients/llm_provider.py).
- **Selects:** provider order from `LLM_PROVIDER_ORDER` (default `openai,groq`); model ids
  from `OPENAI_EXTRACTION_MODEL` / `GROQ_EXTRACTION_MODEL`.
- **Later:** when Component 2B needs an HTTP round trip, this factory is called from the
  `lifespan` block in [backend/src/app/main.py](../../app/main.py) and exposed via
  `app/api/dependencies/`, matching `create_access_token_verifier`.

### G. End-to-End Flow

1. Caller invokes `UserRequirementsInterpretation.interpret(raw_input)`.
2. It calls `parse_unstructured_input(raw_input)`, the mechanism 1 workflow method.
3. Stage 1 normalizes, bounds, and language-gates the input into a `PayloadRecord`.
4. Stage 3 assembles the instruction; the JSON schema is derived from
   `ExtractedRequirements`.
5. Stage 4 calls providers in order until one returns a body, validates it independently,
   and logs which provider answered.
6. Stage 5 pairs the payload with the validated buckets in
   `RequirementInterpretationState` and returns it for Component 2A.

---

## Layer 4 — Backing

- **Mechanism as a method, not a class:** the responsibility is the unit that owns a
  workflow, so a per-mechanism class would add a type whose only job is to hold four methods
  that already share the responsibility's injected providers.
- **One responsibility file:** mechanisms 2–9 read the same state object and the same
  providers, so splitting them across files would mean re-importing and re-injecting the
  same dependencies nine times.
- **One `schemas.py` per service:** the contracts are read by every mechanism of the
  responsibility, so a per-contract file would make each mechanism import from three or four
  modules to see one data journey.
- **Factory beside the client:** `create_places_client` already sits in `google_places.py`,
  so a provider factory in a package `__init__` would be the only place in the repo where
  the factory's location differs from the class it builds.
- **Protocol over ABC:** the repo has no ABCs, and structural typing means the two adapters
  satisfy the contract without an inheritance link to import.
- **Direct `is_english` call:** the predicate has one caller and one implementation, and
  with no test tier there is nothing that needs to substitute it, so injecting it would be a
  parameter no caller ever sets.
- **Raw body as a local value:** the body is needed only long enough to validate it, and no
  component downstream reads it, so carrying it on a contract would persist data with no
  reader.
- **Fallback on transport failure only:** a provider that answers with an out-of-contract
  body is a contract violation, not an availability problem; retrying elsewhere would mask
  it, and Sub-component 4 rejects the whole response.
- **Validation as an independent second check:** strict structured output constrains
  generation, but a truncated or wrapped body still reaches the caller, so the same Pydantic
  model re-checks it.
- **Schema field descriptions as approach 3:** the descriptions travel with the schema to
  the provider, so bucket definitions cannot drift out of sync with the fields they govern.
- **No defaults on wire fields:** strict mode requires every property to be required, which
  is also what makes an empty bucket arrive as `[]` rather than an omitted key.
- **Dataclass state, Pydantic wire:** `extra="forbid"` blocks post-hoc fields, and 2A must
  append to the same object, so the mutable object cannot be the wire model.
- **Prompt text in its own module:** the instruction is a large block of natural-language
  rules plus worked pairs; it is content, not logic, and keeping it out of the class keeps
  the stage methods readable. This is the one file kept apart in the service folder.
- **Logger in the service, printing in the runner:** stage methods emit structured records
  under `DEEP_SEARCH_LOGGER_NAME`, which `LOG_LEVEL` already controls, so terminal
  visibility does not require statements that fire in every future caller of the
  responsibility. The runner is the component that formats and prints, because presentation
  is its only job.
- **Runner calls stages one at a time:** `parse_unstructured_input` returns only the final
  state, so calling the four stages in sequence is what makes each intermediate object
  printable without the workflow method returning debug data it otherwise has no reason to
  expose.
- **Runner reads the raw body off the log:** the body is deliberately not on a contract, so
  the log record stage 4 already emits is the only place it is still readable from outside
  the stage — which is why the runner collects records rather than the stage returning them.
