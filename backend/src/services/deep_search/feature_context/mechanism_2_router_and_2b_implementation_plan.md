# Deep Search — Mechanism 2 Router and Component 2B Implementation Plan

Mechanism 2 of the **User Requirement Interpretation** responsibility: after Component 2A
pass 1, a pass-counted router either forwards the state to Component 2B (generate questions,
CLI collect, persist `user_responses`) then 2A pass 2 (Operation 2 only), or returns the
state so the coordinator can start Mechanism 3 later. Router and 2B are methods on the
existing responsibility class — no new class layer. 2A methods already on the class are
reused, not rewritten.

Architecture and modularity decisions live in
[mechanism_2_router_and_2b_architecture_decisions.md](mechanism_2_router_and_2b_architecture_decisions.md).

Locked decisions: `has_category_flag` is any `target == "category"`; characteristic and
persona flags **never** route to 2B; hard cap is `category_resolution_passes >= 2`; field
name is `state.category_resolution_passes`; the **whole state** is forwarded. Wire models are
Pydantic with `extra="forbid"`; schema name is `CLARIFICATION_QUESTIONS_SCHEMA_NAME`;
**exactly 5** options, one the literal `"other"`; join by `category_id` only. Instruction is
a constants module plus `build_*`; **no taxonomy** inlined; **2** few-shot pairs; id and
phrase shown together. Generation reuses `_call_providers`; one batched call; schema then
coverage; **one retry** on coverage failure only; `ClarificationProviderError` /
`ClarificationValidationError`; coverage failures are validation. CLI stores the selected
option string except `"other"`, which then collects free text. Pass 2 **skips Op1**, runs
Op2 on existing `state.resolved`; 2B at most once; state is **returned** (Mechanism 3 is not
invoked). Tests are pytest with **mocked** provider body and stdin.

## Explicitly out of scope

- **Mechanism 3 and later** are not implemented. After the second inspect, `interpret`
  returns the state.
- **No `DeepSearchFeature` class.** Only Responsibility 1 exists; `interpret` is the
  coordinator.
- **No live-LLM sample runner for 2B.** The harness is pytest (section 4); 2A already has a
  live runner.
- **No new LLM provider, persistence, route, or repository.** The handoff stays in-process.
- **No characteristic or persona clarification.** 2B generates questions only for
  `target: "category"` flags.

---

# 1. File and Module Structure

Placement follows the live layering already in the service: contracts in `feature_schemas/`,
prompt content in `feature_prompts/`, workflow in `requirement_interpretation.py`, error
semantics in `exceptions/`, tests in `backend/tests/`. No file exists per stage — router
and 2B extend the same class in the same file as Mechanism 1 and Component 2A.

### New files — this slice adds 2 source files

| File | Owns | Contains |
| --- | --- | --- |
| [feature_prompts/clarification_instruction.py](../feature_prompts/clarification_instruction.py) | 2B prompt text | task, rules, negative rules, 2 pairs, `build_clarification_questions_instruction` |
| [tests/services/deep_search/test_mechanism_2_clarification.py](../../../../tests/services/deep_search/test_mechanism_2_clarification.py) | assembled-path fixture set | mocked provider + stdin; branch, keys, resolved-unchanged, second inspect |

### Modified files

| File | Change |
| --- | --- |
| [feature_schemas/schemas.py](../feature_schemas/schemas.py) | add `ClarificationQuestion`, `ClarificationResult`, schema builder, schema name; add `category_resolution_passes` on the state |
| [requirement_interpretation.py](../requirement_interpretation.py) | add Mechanism 2 workflow, router, 2B stages; rewire `interpret`; extend `_call_providers` with `provider_error_cls` |
| [exceptions/deep_search.py](../../../exceptions/deep_search.py) | add `ClarificationError` base + `ClarificationProviderError`, `ClarificationValidationError` with `stage` |

`UserResponse` already has `question`, `options`, `response` and is keyed by `int`. No new
composition-root file: `create_requirement_interpretation(settings)` is unchanged.

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| `Router` class / `Component2B` class | methods on `UserRequirementsInterpretation` | locked rule; a mechanism is methods that share the responsibility's providers |
| `clarification_contracts.py` module | fields in the one `schemas.py` | all service contracts stay in one place, as in Mechanism 1 and 2A |
| CLI port / `PromptAdapter` | `input()` and `print()` in the collect method | one stdin channel; tests monkeypatch `input`; no second implementation stated |
| Merge 2B prompt into `category_resolution_instruction.py` | own `clarification_instruction.py` | 2A's file owns mapping/resolution; 2B's rules change independently |
| Retry / backoff layer | one inline second `_call_providers` on coverage failure | schema failure is a contract violation; only coverage gets one retry |
| `DeepSearchFeature` coordinator class | `interpret` returns the state | only Responsibility 1 exists; Mechanism 3 is out of scope |

---

# 2. Architecture and Modularity Decisions

See [mechanism_2_router_and_2b_architecture_decisions.md](mechanism_2_router_and_2b_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation — raw input → per-category specification
   ├─ Mechanism 1 Workflow: parse_unstructured_input — unstructured input → extracted buckets
   └─ Mechanism 2 Workflow: run_explicit_category_resolution — map, maybe clarify, re-resolve
      ├─ 2A pass 1: resolve_explicit_categories — Op1 always; Op2 skipped (responses empty)
      ├─ Router: inspect_category_resolution — increment passes; emit component_2b or mechanism_3
      ├─ (contract) ClarificationResult schema — see §B, not a runtime method
      ├─ 2B Stage 1: build_clarification_questions_instruction — rules + schema + 2 pairs
      ├─ 2B Stage 2: execute_clarification_questions — one call → ClarificationResult or typed error
      ├─ 2B Stage 3: collect_clarification_responses — numbered CLI; write user_responses
      ├─ 2A pass 2: resolve_category_flags — Op1 skipped; Op2 on existing state.resolved
      ├─ Router: inspect_category_resolution — cap or zero category flags → mechanism_3
      └─ (harness) assembled-path fixture checks — test-only, not in request path
```

The schema is a **contract** (§B). The fixture set is **test-only** and excluded from §E.
`resolve_explicit_categories` stays Component 2A; it is no longer the Mechanism 2 workflow
name. There is no `DeepSearchFeature` node because only Responsibility 1 exists.

## B. Data Contracts

All of these live in [feature_schemas/schemas.py](../feature_schemas/schemas.py), except the
error types in [exceptions/deep_search.py](../../../exceptions/deep_search.py).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `ClarificationQuestion` | one generated question | `category_id: int` — echoed flag id · `category: str` — flagged phrase · `question: str` · `options: list[str]` — exactly 5, one is `"other"` | wire model | Stage 2 → Stage 3 |
| `ClarificationResult` | batched generation output | `questions: list[ClarificationQuestion]` — one per submitted category flag | wire model | Stage 2 → Stage 3 |
| `UserResponse` *(existing)* | one stored CLI answer | `question: str` · `options: list[str]` · `response: str` — selected option, or free text when `"other"` | wire model | Stage 3 → 2A Op2 |
| `RequirementInterpretationState` *(extended)* | mutable workflow state | existing fields plus `category_resolution_passes: int` (default `0`) | **mutable** — router increments; 2B writes `user_responses` | M1 → 2A → router → 2B → 2A |
| `CategoryResolutionRoute` | router destination | `Literal["component_2b", "mechanism_3"]` | immutable | Router → workflow method |
| `ClarificationError` | 2B failure base with `stage` | `message: str` · `stage: str` — default `execute_clarification_questions` | immutable | Stage 2 → caller |
| `ClarificationProviderError` | no provider returned a body | inherits `ClarificationError` | immutable | Stage 2 → caller |
| `ClarificationValidationError` | body failed schema or coverage | inherits `ClarificationError` | immutable | Stage 2 → caller |

Rules surfaced here: join questions to flags by `category_id`, not list order; `options` is
length 5 with exactly one `"other"` (schema validation, not coverage); empty `questions`
while flags were submitted is a coverage miss; `resolved.*` is not a 2B write; 2B does not
increment `category_resolution_passes`; `user_responses` stays `dict[int, UserResponse]`.

`clarification_questions_json_schema()` derives from `ClarificationResult` and reuses
`_apply_strict_object_rules`. No taxonomy `enum` — 2B does not select a node.

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol *(reused)* | `generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict [raises: LLMProviderError]` | `OpenAIStructuredProvider`, `GroqStructuredProvider` | Stage 2 |
| `clarification_questions_json_schema` | schema derivation | `() -> dict` — strict 2B schema, closed objects, no taxonomy enum | one | Stage 1, Stage 2 |
| `build_clarification_questions_instruction` | function | `(json_schema: dict) -> str` — task, rules, schema, 2 pairs | one | Stage 1 |
| stdin / stdout | runtime I/O | `input(prompt: str) -> str`; `print(...)` | builtins; tests monkeypatch `input` | Stage 3 |

No new provider. Composition root unchanged. Why the protocol is reused lives in the
architecture file.

## D. Class and Method Blueprint

**`UserRequirementsInterpretation`** — in [requirement_interpretation.py](../requirement_interpretation.py).
Router and 2B add the methods below; they read the same state and provider chain as
Mechanism 1 and 2A. Existing 2A methods stay. Pass 2 calls `resolve_category_flags` only.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `interpret` | `(raw_input: str) -> RequirementInterpretationState [raises: CategoryResolutionError, ClarificationError]` | parse, run Mechanism 2, return state |
| `run_explicit_category_resolution` | `(state: RequirementInterpretationState) -> RequirementInterpretationState [raises: CategoryResolutionError, ClarificationError]` | drive 2A, router, maybe 2B and pass 2 |
| `inspect_category_resolution` | `(state: RequirementInterpretationState) -> CategoryResolutionRoute [mutates: state.category_resolution_passes]` | increment passes; emit 2B or Mechanism 3 |
| `clarify_unmapped_categories` | `(state: RequirementInterpretationState) -> None [raises: ClarificationError] [mutates: state.user_responses]` | generate questions, collect answers, persist |
| `build_clarification_questions_instruction` | `(json_schema: dict) -> str` | assemble rules, schema, two worked pairs |
| `execute_clarification_questions` | `(state: RequirementInterpretationState, instruction: str) -> ClarificationResult [raises: ClarificationProviderError, ClarificationValidationError]` | one constrained call, validate, coverage retry |
| `collect_clarification_responses` | `(state: RequirementInterpretationState, result: ClarificationResult) -> None [mutates: state.user_responses]` | numbered CLI; persist answers by category_id |

**Module-level functions**

| Function | Module | Signature | Purpose (one line) |
| --- | --- | --- | --- |
| `clarification_questions_json_schema` | `feature_schemas/schemas.py` | `() -> dict` | strict 2B schema, closed objects |
| `build_clarification_questions_instruction` | `feature_prompts/clarification_instruction.py` | `(json_schema: dict) -> str` | 2B instruction assembly |
| `_call_providers` *(extended)* | `requirement_interpretation.py` | `(*, instruction, user_content, json_schema, schema_name, stage, provider_error_cls=CategoryMappingProviderError) -> tuple[dict, str] [raises: provider_error_cls]` | try providers in order; raise the given error class |

`interpret` calls `parse_unstructured_input` then `run_explicit_category_resolution`. It
does not call Mechanism 3.

## E. Runtime Flow — Data Object Journey

Test harness excluded — not in the request path.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `parse_unstructured_input` | `raw_input: str` | state with `extracted` | `user_responses={}`, `resolved=None`, `passes=0` |
| 2 | `resolve_explicit_categories` | state (`extracted`) | `state.resolved` | category flags may remain; Op2 skipped |
| 3 | `inspect_category_resolution` | `state.resolved.ambiguity_flags` | `passes += 1`; route | `passes=1`; `component_2b` or `mechanism_3` |
| 4 | *(branch)* | route | skip 2B when `mechanism_3` | return state, or continue |
| 5 | `build_clarification_questions_instruction` | `clarification_questions_json_schema()` | `instruction: str` | state unchanged |
| 6 | `execute_clarification_questions` | state, instruction, providers | `ClarificationResult` **or** typed error | `resolved.*` unchanged |
| 7 | `collect_clarification_responses` | result, stdin | `state.user_responses[category_id]` | one `UserResponse` per category flag; `passes` still 1 |
| 8 | `resolve_category_flags` | `state.resolved`, `user_responses` | mutates `state.resolved` | category flags gone; Op2 entries appended |
| 9 | `inspect_category_resolution` | flags, `passes` | `passes += 1`; route `mechanism_3` | `passes=2`; return state |

**Transformation trace (shape only):**

```
RequirementInterpretationState{ payload, extracted, user_responses={}, resolved=None, category_resolution_passes=0 }
 → state.resolved = ResolvedRequirements{ ..., ambiguity_flags[] }     # 2A pass 1; category flags may remain
 → category_resolution_passes=1, route: "component_2b" | "mechanism_3"
 → (+ clarification instruction, + json_schema)
 → dict                                                                # raw 2B body, local to stage 6
 → ClarificationResult{ questions[] }
   | ClarificationProviderError | ClarificationValidationError         # stage 6 exits
 → user_responses{ category_id: UserResponse{ question, options, response } }   # resolved.* unchanged
 → state.resolved  (resolved_explicit_categories += Op2 entries; category flags removed)
 → category_resolution_passes=2, route: "mechanism_3"
 → return state
```

**Approach at the real decision points:**

- Router increments `category_resolution_passes` first, then branches. Cap (`passes >= 2`)
  is checked before `has_category_flag`, so a leftover category flag after pass 2 cannot
  re-enter 2B.
- Only `target == "category"` sets the 2B branch. Characteristic and persona flags fall
  through to `mechanism_3`.
- The workflow method is the only 2B caller. 2B runs at most once per request.
- Generation: one `_call_providers` with `CLARIFICATION_QUESTIONS_SCHEMA_NAME` and
  `ClarificationProviderError`. The body is validated as `ClarificationResult`. Schema
  failure (wrong shape, options not length 5, `"other"` missing) is an immediate
  `ClarificationValidationError` — no retry. Coverage then requires returned `category_id`
  values to equal the submitted flag ids, with no duplicates. A coverage miss repeats the
  same instruction, schema, and user content once. A second coverage miss is
  `ClarificationValidationError`. Total provider failure on either attempt is
  `ClarificationProviderError`. Both errors carry `stage="execute_clarification_questions"`.
- CLI: present in submitted-flag order; look up each question by `category_id`. Print a
  taxonomy-scope preface, the category phrase, the question, and options numbered 1 to 5.
  The customer types an index. Blank, non-integer, or out-of-range reprints the same
  question. Selected `"other"` then collects a non-empty free-text line as `response`;
  otherwise `response` is the option string. Key is `category_id`. `resolved.*` and the
  pass counter are untouched.
- Pass 2 does not call `resolve_explicit_categories`. It calls `resolve_category_flags`,
  which pairs each remaining category flag with `user_responses[category_id]`.
- After the second inspect, `interpret` returns. Mechanism 3 is not called.

## F. Method Detail

**`run_explicit_category_resolution`**

- **Purpose:** sequence 2A, the router, 2B, and 2A pass 2 for one request.
- **What it does:** run 2A pass 1; inspect; on `mechanism_3`, return; on `component_2b`, run
  `clarify_unmapped_categories`, then `resolve_category_flags`, inspect again, return. Does
  not invoke 2B a second time.
- **Inputs:** state after Mechanism 1 · **Outputs:** same state · **Failure:** 2A or 2B typed
  errors.

**`inspect_category_resolution`**

- **Purpose:** own the pass counter and emit one binary route.
- **What it does:** increment `category_resolution_passes` by 1. When `passes >= 2`, emit
  `mechanism_3`. When `resolved` is missing or has no `target=="category"` flag, emit
  `mechanism_3`. Otherwise emit `component_2b`. Forwards the whole state by mutating it in
  place and returning only the route.
- **Inputs:** `state` · **Outputs:** `CategoryResolutionRoute` · **Failure:** none.

**`execute_clarification_questions`**

- **Purpose:** return one schema-valid result covering every submitted id, or a typed failure.
- **What it does:** take submitted ids from `target=="category"` flags; send instruction as
  the system message and the flags-plus-grounding block as user content; try providers in
  the bound order; validate the first body against `ClarificationResult`; schema failure
  rejects with no retry; coverage failure repeats the same call once; a second coverage
  miss rejects; do not write state.
- **Inputs:** `state`, `instruction` · **Outputs:** `ClarificationResult` · **Failure:**
  `ClarificationProviderError` (no provider answered), `ClarificationValidationError`
  (schema or coverage).

**`collect_clarification_responses`**

- **Purpose:** store one non-empty answer per question, keyed by `category_id`.
- **What it does:** for each submitted flag, look up its question by `category_id`; print
  that this category could not be mapped to a known amenity type and that the customer
  should pick what they meant, not a new need; print category, question, numbered options;
  prompt for an index 1–5; reprint on blank, non-integer, or out-of-range; on `"other"`,
  prompt for a non-empty description and store that line; otherwise store the option
  string; write `UserResponse` at `user_responses[category_id]`; continue to the next flag.
- **Inputs:** `state`, `result` · **Outputs:** none · **Failure:** none (re-prompts until
  a valid answer).

**`build_clarification_questions_instruction`**

- **Purpose:** produce the system instruction that forbids discovery, preference, and bundling.
- **What it does:** concatenate task statement, rules, negative rules, closed schema, and 2
  worked pairs; no taxonomy list; few-shots show flags as id and phrase together and one
  question per flag with 5 options including `"other"`. Live flags and grounding travel as
  user content, not inside this string: submitted `{category_id, category}`, plus
  `resolved_explicit_categories`, `payload`, `persona_facts`, and full `ambiguity_flags`.
- **Inputs:** `json_schema` · **Outputs:** `str` · **Failure:** none.

---

# 4. Assembled-Path Fixture Set

The pytest file is a dev check, not part of the request path in §E. No real provider
calls. No new settings.

## 4.1 Running it

From `backend/`:

`pytest tests/services/deep_search/test_mechanism_2_clarification.py`

## 4.2 What the harness does

It constructs `UserRequirementsInterpretation` with a fake `StructuredLLMProvider` whose
`generate_structured` returns a recorded dict. It monkeypatches `input` with a queue of
index strings (and a free-text line when `"other"` is selected). It seeds
`RequirementInterpretationState` as after 2A pass 1.

| Check | Asserts |
| --- | --- |
| pass-1 category flag | inspect emits `component_2b` |
| pass-1 characteristic/persona only | inspect emits `mechanism_3` |
| after 2B persist | `user_responses` keys equal submitted `category_id`s; each value is a `UserResponse` |
| after 2B resolved | `resolved.*` equals the pre-2B snapshot |
| after pass 2 + second inspect | route is `mechanism_3`; generate is not called again |
| hard cap | `passes >= 2` emits `mechanism_3` even with a category flag |
| coverage retry | first body missing an id triggers a second provider call; second miss raises `ClarificationValidationError` |
| `"other"` path | stored `response` is the typed free text, not the string `"other"` |
