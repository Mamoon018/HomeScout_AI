# Deep Search — Mechanism 1 Implementation Plan

Mechanism 1 (Unstructured Input Parsing) of the **User Requirement Interpretation**
responsibility: a single-pass, provider-constrained LLM extraction that turns raw customer
text into a validated four-bucket intermediate representation. It is the first LLM
integration in the backend, so it also introduces the `StructuredLLMProvider` seam with
OpenAI primary and Groq fallback.

Architecture and modularity decisions live in
[mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).

Locked decisions: failures **raise typed exceptions**; non-English rejection uses a
**pinned language-detection dependency** (`langdetect`, seeded).

## Explicitly out of scope

- **Sub-component 6 is not implemented.** No fixture set, no rubric scoring, no test files,
  no automated assertions. Nothing here produces a test.
- A **manual sample-run script is in scope** and is not a test: it makes one real LLM call
  and prints what each stage returned. See section 4.
- **No run-artifact record.** The raw provider body is a local value inside stage 4,
  validated and then discarded; it is not carried on any contract.
- **No `user_responses` field.** Collecting customer answers belongs to Component 2B.
- No route, repository, or persistence: Sub-component 5 fixes the handoff as an in-process
  typed return.

---

# 1. File and Module Structure

Placement follows the repo's existing layering: SDK calls in `clients/`, business workflow
in `services/<feature>/`, error semantics in `exceptions/`. No file exists per contract, per
mechanism, or per stage.

### New files — the whole mechanism is 7 source files

| File | Owns | Contains |
| --- | --- | --- |
| [backend/src/clients/llm_provider.py](../../clients/llm_provider.py) | all structured-LLM communication | `StructuredLLMProvider` protocol, `OpenAIStructuredProvider`, `GroqStructuredProvider`, `create_openai_provider`, `create_groq_provider`, `create_llm_providers` |
| [backend/src/exceptions/llm.py](../../exceptions/llm.py) | client-layer error semantics | `LLMProviderError`, `LLMResponseTruncatedError` |
| [backend/src/exceptions/deep_search.py](../../exceptions/deep_search.py) | service-layer failure surface | `RequirementExtractionError` and its four subclasses |
| [schemas.py](schemas.py) | every data contract of the Deep Search service | Sub-component 2 wire models, `extraction_json_schema()`, `PayloadRecord`, `RequirementInterpretationState` |
| [extraction_instruction.py](extraction_instruction.py) | Sub-component 3 prompt text | bucket definitions, negative rules, boundary rules, few-shot pairs, `build_few_shot_examples()` |
| [requirement_interpretation.py](requirement_interpretation.py) | Responsibility 1 in full — all mechanisms | `UserRequirementsInterpretation`, `is_english`, `create_requirement_interpretation` |
| [requirement_interpretation_sample_run.py](requirement_interpretation_sample_run.py) | manual run entry point, terminal output | `SAMPLE_CUSTOMER_INPUT`, `run_sample_extraction()`, `main()` with `--input-file` |

Plus an empty `__init__.py` marker for `backend/src/services/deep_search/`.

The runner follows the existing precedent in
[backend/src/services/google_places_sample_run.py](../google_places_sample_run.py): a dev
script beside the service it exercises, building its dependencies from `get_settings()`.

Mechanisms 2 through 9 of this responsibility add **methods to the same class in the same
file**, not new files.

### Modified files

| File | Change |
| --- | --- |
| [backend/src/core/config.py](../../core/config.py) | added `openai_api_key`, `openai_extraction_model`, `groq_api_key`, `groq_extraction_model`, `llm_provider_order` |
| [backend/src/core/logging.py](../../core/logging.py) | added `DEEP_SEARCH_LOGGER_NAME`, following `PLACES_LOGGER_NAME` |
| [backend/requirements.txt](../../../requirements.txt) | pinned `openai==3.10.0`, `groq==1.7.0`, `langdetect==1.0.9` and their new transitive pins |
| [backend/.env.example](../../../.env.example) | documents the five new vars, and notes `LOG_LEVEL=DEBUG` for full stage output |

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| `clients/llm/` package of 4 files | one `clients/llm_provider.py` | matches `google_places.py`: factory sits beside the client it builds |
| `create_llm_providers` in `__init__.py` | in `clients/llm_provider.py` | package markers stay empty; logic is importable from a named module |
| `utils/language.py` | `is_english` in `requirement_interpretation.py` | one consumer, one caller; no `utils/` layer needed for it |
| `intermediate_representation.py` + `contracts.py` | one `schemas.py` | all service data contracts in one place, per service |
| `mechanism_1_input_parsing.py` + `responsibility.py` | one `requirement_interpretation.py` | the responsibility is one class; mechanisms are its methods |
| `requirement_interpretation/` subpackage | flat files in `deep_search/` | three modules do not need a package nesting level |
| test files, fixtures, rubric script | none | Sub-component 6 is out of scope |

---

# 2. Architecture and Modularity Decisions

See [mechanism_1_architecture_decisions.md](mechanism_1_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation — raw input → per-category specification
   └─ Mechanism 1 Workflow: parse_unstructured_input — unstructured input → separated buckets
      ├─ Stage 1: intake_and_assemble_payload — validate, normalize, keep raw
      ├─ Stage 2: (contract) ExtractedRequirements schema — see §B, not a runtime method
      ├─ Stage 3: build_extraction_instruction — bucket rules + negative rules + few-shot
      ├─ Stage 4: execute_and_validate — ordered constrained call, then independent validation
      └─ Stage 5: assemble_handoff — pair payload with buckets as the mutable state object
```

Stage 2 is the one node that is not a runtime method; it is a contract (§B). Sub-component 6
has no node because it is out of scope. There is no `DeepSearchFeature` node because only
Responsibility 1 exists.

## B. Data Contracts

All of these live in [schemas.py](schemas.py).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `PayloadRecord` | bounded, normalized input for the call | `normalized_text: str` — cleaned, markup preserved · `raw_text: str` — untouched original | frozen | Stage 1 → Stage 4, Stage 5 |
| `ExtractedCategory` | one stated category and its traits | `name: str` — customer's wording · `characteristics: list[str]` — `[]` never null | wire model | provider → 2A |
| `AmbiguityFlag` | one phrase with competing readings | `phrase: str` · `target: Literal["category","characteristic","persona"]` | wire model | provider → 2A |
| `ExtractedRequirements` | the four separated buckets | `explicit_categories: list[ExtractedCategory]` · `ambiguity_flags: list[AmbiguityFlag]` · `persona_facts: list[str]` | closed, no defaults | Stage 4 → Stage 5, 2A |
| `RequirementInterpretationState` | the handoff object 2A receives | `payload: PayloadRecord` — context 2A resolves against · `extracted: ExtractedRequirements` | **mutable** | Stage 5 → 2A |

Rules surfaced here: buckets (a) and (b) collapse into `explicit_categories` because
characteristics nest under their category; every bucket is a required key so empty arrives
as `[]`; `extra="forbid"` on every wire model emits `additionalProperties: false` on itself
and its nested definitions; `RequirementInterpretationState` is the one mutable object,
because Component 2A appends its resolved categories to the same object rather than
reconstructing it.

`extraction_json_schema()` derives the provider schema from `ExtractedRequirements` and then
walks the tree to close every object node — `additionalProperties: false` plus a `required`
list holding every property — which is what both providers demand of a `strict: true`
schema.

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol | `name: str`, `model: str`, `generate_structured(*, instruction: str, user_content: str, json_schema: dict, schema_name: str) -> dict [raises: LLMProviderError]` | `OpenAIStructuredProvider`, `GroqStructuredProvider` | Stage 4 |
| `extraction_json_schema` | schema derivation | `() -> dict` — strict JSON schema from `ExtractedRequirements` | one | Stage 3, 4 |
| `is_english` | predicate | `(text: str) -> bool` | one, called directly | Stage 1 |
| `Settings` | config | `openai_api_key`, `groq_api_key`, model ids, `llm_provider_order` | one | composition root |

Providers expose read-only `name` and `model` so stage 4 can log which one answered and on
which model, without the stage reaching into an SDK client.

## D. Class and Method Blueprint

**`UserRequirementsInterpretation`** — in [requirement_interpretation.py](requirement_interpretation.py).
Responsibility 1 entry; holds the ordered providers. Mechanisms 2–9 add methods here.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | `(providers: Sequence[StructuredLLMProvider]) -> None` | bind the ordered provider chain |
| `interpret` | `(raw_input: str) -> RequirementInterpretationState [raises: RequirementExtractionError]` | responsibility entry; sequences mechanisms |
| `parse_unstructured_input` | `(raw_input: str) -> RequirementInterpretationState [raises: RequirementExtractionError]` | mechanism 1 workflow; drives stages 1, 3, 4, 5 |
| `intake_and_assemble_payload` | `(raw_input: str) -> PayloadRecord [raises: InputTooShortError, UnsupportedLanguageError]` | validate encoding and length, normalize, keep raw |
| `build_extraction_instruction` | `(json_schema: dict) -> str` | assemble bucket rules, negative rules, few-shot pairs |
| `execute_and_validate` | `(payload: PayloadRecord, instruction: str) -> ExtractedRequirements [raises: ExtractionProviderError, ExtractionValidationError]` | try providers in order, then validate independently |
| `assemble_handoff` | `(payload: PayloadRecord, extracted: ExtractedRequirements) -> RequirementInterpretationState` | pair payload and buckets as the mutable handoff |

**`OpenAIStructuredProvider`** / **`GroqStructuredProvider`** — in
[clients/llm_provider.py](../../clients/llm_provider.py). SDK adapters, identical surface.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | `(client: SDKClient, *, model: str) -> None` | bind an authenticated SDK client and model id |
| `name` | `property -> str` | provider label used in the stage 4 log line |
| `model` | `property -> str` | model id used in the stage 4 log line |
| `generate_structured` | `(*, instruction: str, user_content: str, json_schema: dict, schema_name: str) -> dict [raises: LLMProviderError]` | one strict schema-constrained call, decoded to dict |

**Module-level functions**

| Function | Module | Signature | Purpose (one line) |
| --- | --- | --- | --- |
| `create_openai_provider` | `clients/llm_provider.py` | `(settings: Settings) -> OpenAIStructuredProvider` | authenticated OpenAI adapter from config |
| `create_groq_provider` | `clients/llm_provider.py` | `(settings: Settings) -> GroqStructuredProvider` | authenticated Groq adapter from config |
| `create_llm_providers` | `clients/llm_provider.py` | `(settings: Settings) -> tuple[StructuredLLMProvider, ...]` | ordered tuple resolved from `llm_provider_order` |
| `create_requirement_interpretation` | `requirement_interpretation.py` | `(settings: Settings) -> UserRequirementsInterpretation` | composition root for the responsibility |
| `is_english` | `requirement_interpretation.py` | `(text: str) -> bool` | language gate with a pinned detector seed |
| `extraction_json_schema` | `schemas.py` | `() -> dict` | strict provider schema derived from the wire model |
| `build_few_shot_examples` | `extraction_instruction.py` | `() -> tuple[tuple[str, str], ...]` | fixed worked input/output pairs for the instruction |

`MIN_INPUT_WORD_COUNT = 100` is a module constant in `requirement_interpretation.py`, not a
parameter.

## E. Runtime Flow — Data Object Journey

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `intake_and_assemble_payload` | `raw_input: str` | `PayloadRecord` | `{normalized_text, raw_text}` |
| 2 | `build_extraction_instruction` | `extraction_json_schema()` | `instruction: str` | payload unchanged |
| 3 | `execute_and_validate` | payload, instruction, provider tuple | `ExtractedRequirements` **or** typed error | 3 required keys present, empties `[]` |
| 4 | `assemble_handoff` | payload, extracted | `RequirementInterpretationState` | `{payload, extracted}` |

**Transformation trace (shape only):**

```
str
 → PayloadRecord{ normalized_text, raw_text }
 → (+ instruction, + json_schema)
 → dict                                          # raw provider body, local to stage 4
 → ExtractedRequirements{ explicit_categories[], ambiguity_flags[], persona_facts[] }
 → RequirementInterpretationState{ payload, extracted }                    # handed to 2A
    | InputTooShortError | UnsupportedLanguageError                        # stage 1 exits
    | ExtractionProviderError | ExtractionValidationError                  # stage 4 exits
```

**Approach at the real decision points:**

- Intake runs in a fixed order so each check sees usable text: normalize first, then reject
  empty or whitespace-only, then reject under 100 words, then reject non-English.
- Empty, whitespace-only, and under-limit inputs raise the same error with the message
  `Instructions must be of more than 100 words`; there is no maximum length. Whitespace-only
  input normalizes to zero words, so the word bound is the single check that catches all
  three.
- Normalization preserves line breaks, bullets, and quotes because they carry list structure
  the model reads as separate statements; it collapses only horizontal whitespace runs and
  strips control and format characters (BOM, zero-width) other than newline and tab. No
  character offsets are kept.
- Providers are tried in the bound order; the next provider is attempted **only** when the
  current one fails to return a body.
- Which provider is primary is decided at the composition root, never inside the stage.
- The raw body lives only inside stage 4: it is decoded, validated, and dropped once the
  typed contract exists.
- Validation is an independent second check after generation-time constraint, and it is
  all-or-nothing: any missing, extra, or ill-typed field rejects the whole response with no
  partial acceptance.
- A validation failure does **not** fall back to the next provider; an out-of-contract body
  is a contract violation, not an availability problem.
- Two distinct exits name their cause: `ExtractionProviderError` when no provider returned a
  body, `ExtractionValidationError` when a body failed validation. Every subclass carries a
  `stage` class attribute so a caller can report where the exit happened without reading a
  traceback.

## F. Method Detail

**`intake_and_assemble_payload`**

- **Purpose:** produce one bounded, normalized payload so behavior tracks content, not
  formatting.
- **What it does:** Unicode-normalizes (NFKC); normalizes line endings; strips BOM,
  zero-width, and control characters except newline and tab; collapses horizontal whitespace
  while preserving line breaks, bullets, and quotes; rejects empty, whitespace-only, and
  under-`MIN_INPUT_WORD_COUNT` input with the same message; rejects non-English via
  `is_english`; keeps the raw text alongside the normalized text.
- **Inputs:** `raw_input: str` · **Outputs:** `PayloadRecord` · **Failure:**
  `InputTooShortError`, `UnsupportedLanguageError`.

**`build_extraction_instruction`**

- **Purpose:** make one call fill the schema with each phrase in exactly one bucket.
- **What it does:** combines all three approaches — written per-bucket definitions plus
  negative rules in the instruction, the cross-bucket boundary rule set stated globally, and
  per-bucket definitions carried in the schema field descriptions; appends fixed worked
  pairs covering a rich input, a thin input, an ambiguous phrase, and a negation.
- **Locked rules it encodes:** an explicit category is one the user directly names or
  clearly refers to as wanted, preferred, needed, avoided, or considered, without inferring
  from unrelated context; a phrase is ambiguous when it has two or more reasonable readings
  leading to different categories, characteristics, or scopes and the input gives no
  confident basis to pick one; ambiguity may be flagged against a category, a
  characteristic, or a persona fact; a negation or conditional that does not name a category
  goes to persona/situation/lifestyle facts, while a category named as one to avoid stays an
  explicit category with the avoidance recorded as a characteristic; do not map to any
  category list; do not add a category the user did not state; no upper bound on items per
  bucket.
- **Inputs:** `json_schema: dict` · **Outputs:** `str` · **Failure:** none.

**`execute_and_validate`**

- **Purpose:** return one schema-valid contract or a typed failure naming the stage.
- **What it does:** iterates the bound provider order; each provider sends the instruction
  as the system message and `payload.normalized_text` as the user content with the strict
  JSON schema attached; a provider error or a truncated body moves to the next provider; the
  first returned body is validated once against `ExtractedRequirements`, any violation
  rejects it outright, and the answering provider's `name` is logged.
- **Inputs:** `payload: PayloadRecord`, `instruction: str` · **Outputs:**
  `ExtractedRequirements` · **Failure:** `ExtractionProviderError`,
  `ExtractionValidationError`.

**`generate_structured`** (both adapters)

- **Purpose:** one schema-constrained call, decoded, with SDK errors mapped locally.
- **What it does:** sends a system-plus-user pair with `response_format` set to the strict
  `json_schema`; treats a `length` finish reason as truncation; decodes the body to a dict;
  maps auth, rate-limit, timeout, and decode failures onto `LLMProviderError` so no SDK type
  escapes `clients/`.
- **Inputs:** instruction, user content, schema, schema name · **Outputs:** `dict` ·
  **Failure:** `LLMProviderError`, `LLMResponseTruncatedError`.

---

# 4. Manual Run Guide and Terminal Output

The runner is a dev entry point, not part of the request path in §E.

## 4.1 One-time setup

1. From `backend/`, install the updated pins: `pip install -r requirements.txt` (adds
   `openai`, `groq`, `langdetect`).
2. Add to `backend/.env`:

| Var | Value | Why |
| --- | --- | --- |
| `OPENAI_API_KEY` | your key | primary provider |
| `GROQ_API_KEY` | your key | fallback provider |
| `OPENAI_EXTRACTION_MODEL` | a strict-structured-output model (default `gpt-4o-2024-08-06`) | `response_format` with `strict: true` must be supported |
| `GROQ_EXTRACTION_MODEL` | a JSON-schema-capable model (default `openai/gpt-oss-120b`) | same requirement on the fallback |
| `LLM_PROVIDER_ORDER` | `openai,groq` | first entry is primary |
| `LOG_LEVEL` | `DEBUG` | DEBUG prints full objects to stderr; INFO prints summaries only |

`OPENAI_API_KEY` and `GROQ_API_KEY` are required settings; the three others have the
defaults shown above. Confirm both model ids support strict JSON-schema structured output
before the first run; a model without it will fail validation rather than return a wrong
answer.

## 4.2 Running it

From `backend/`:

- Default sample input:
  `python -m src.services.deep_search.requirement_interpretation_sample_run`
- Your own input:
  `python -m src.services.deep_search.requirement_interpretation_sample_run --input-file path/to/requirements.txt`

Each run makes **one** extraction call. `SAMPLE_CUSTOMER_INPUT` is a built-in requirement
text of 191 words, so the default run clears intake.

## 4.3 What the runner does

It builds the responsibility through `create_requirement_interpretation(get_settings())`,
calls `configure_logging(settings.log_level)` the way `main.py` does, then calls the four
stages **in sequence rather than through `parse_unstructured_input`**, printing a titled
section after each one:

| Section printed | Content |
| --- | --- |
| `INPUT` | raw text, character count, word count |
| `STAGE 1 - PAYLOAD` | `PayloadRecord` as dict; normalized text in full; raw vs normalized lengths |
| `STAGE 2 - SCHEMA` | `extraction_json_schema()` pretty-printed; confirms `additionalProperties: false` and the required list on the root and every `$def` |
| `STAGE 3 - INSTRUCTION` | the assembled instruction in full, plus its character count and few-shot pair count |
| `STAGE 4 - PROVIDER ATTEMPTS` | one line per attempt: provider name, model, outcome; then the raw decoded body pretty-printed |
| `STAGE 4 - VALIDATED` | `ExtractedRequirements` via `model_dump_json(indent=2)` |
| `STAGE 5 - HANDOFF` | `RequirementInterpretationState` as dict, and a per-bucket count summary |

Stage 4 discards the raw body once the typed contract exists, so the runner attaches a
collecting log handler and reads the attempt lines and the raw body back off the service's
own `DEEP_SEARCH_LOGGER_NAME` records. It opens that logger to `DEBUG` for the run so those
sections are complete whatever `LOG_LEVEL` says; the stderr handler still honours
`LOG_LEVEL`.

On a typed failure it catches `RequirementExtractionError`, prints the exception class, its
`stage`, and the message, and exits non-zero. Nothing is written to disk.

## 4.4 Stage logging inside the service

Every stage method and both adapters emit one structured record under
`DEEP_SEARCH_LOGGER_NAME`, following the `logger.info(json.dumps({...}))` shape already used
in [google_places.py](../../clients/google_places.py). Summaries at INFO, full objects at
DEBUG, so the same visibility is available from any caller without the runner.

| Emitter | INFO record | DEBUG adds |
| --- | --- | --- |
| `intake_and_assemble_payload` | raw length, normalized length, word count, language verdict | full normalized text |
| `build_extraction_instruction` | instruction length, few-shot count, schema property names | full instruction text |
| `execute_and_validate` | per attempt: provider name, model, outcome; then validation verdict | full raw body, per-bucket counts |
| `assemble_handoff` | counts per bucket | full state as dict |
| `generate_structured` | provider, model, finish reason, response length | full response content |

Rejections log the reason before raising, so an under-limit or non-English input is visible
in the terminal rather than only as a traceback.

The word count appears in the log line and in the runner's `INPUT` section even though it is
not a `PayloadRecord` field: intake computes it locally to check the bound, logs it, and
discards it.

## 4.5 Exercising the branches by hand

| To see | Do this |
| --- | --- |
| under-limit rejection | `--input-file` pointing at a file under 100 words |
| non-English rejection | `--input-file` with a long non-English text |
| provider switch | set `LLM_PROVIDER_ORDER=groq,openai` and re-run |
| fallback engaging | invalidate `OPENAI_API_KEY`, keep the order, and watch attempt 1 fail and attempt 2 answer |
| validation rejection | point `OPENAI_EXTRACTION_MODEL` at a model without strict structured output |

---

## Items settled during implementation

- **Few-shot vocabulary.** Sub-component 3's decision read both ways: "examples use project
  amenity vocabulary", followed by the reason against it — "using it pulls the model toward
  taxonomy mapping, which is locked out of this component." The implementation follows the
  reasoning and keeps the worked examples in **neutral, non-taxonomy wording**, since
  taxonomy mapping is Component 2A's job.
- **Avoidance vs negation.** The bucket rules said both "an explicit category is one the
  user names as … avoided" and "negations go to persona facts, never to the explicit
  bucket". These are reconciled in `BOUNDARY_RULES`: a **named category** the customer wants
  to avoid stays an explicit category with the avoidance as one of its characteristics,
  while a negation or conditional that **names no category** ("we don't drive", "no interest
  in nightlife") is a persona fact. Read the other way, "avoided" in the bucket definition
  would be dead text.
- **`model` on the provider protocol.** §4.3 and §4.4 both put the model id in the stage 4
  attempt line, so the protocol exposes a read-only `model` beside `name`. Without it the
  stage would have to reach into an SDK client to log what it was told to log.
