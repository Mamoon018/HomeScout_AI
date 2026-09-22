# Deep Search — Mechanism 5 Implementation Plan

Mechanism 5 of the **User Requirement Interpretation** responsibility: after Mechanism 4
has written `state.inferred_categories`, one batched constrained LLM call assigns a depth
to every remaining category. Floors differ by origin (explicit = `operating_details`,
inferred = `basic_profile`). Code rejects an explicit `basic_profile` and an id-set
mismatch. It stamps `depth` onto existing entries. It does not emit metrics, fetch, or mix
lists. Depth calibration is methods on the existing responsibility class — no new class
layer. Mechanism 3 stays excluded.

Architecture and modularity decisions live in
[mechanism_5_architecture_decisions.md](mechanism_5_architecture_decisions.md).

Locked decisions: input is the `RequirementInterpretationState` after Mechanism 4
(`state.resolved` is set, `inferred_categories` is written); both lists empty skips
Operations 1–4, leaves lists unchanged, does not call the model, and does not fail; at
least one category runs one batched call; thin or empty `persona_facts` /
`characteristics` is not a skip; scale is prompt text, not a per-`taxonomy_node` lookup;
wire schema allows all three depths; code rejects explicit `basic_profile` before stamp;
code does not fill, drop, or clamp; model body fields are `category_id` and `depth` only;
metric contract is instruction text for Mechanism 6 / retrieval; `interpret()` sequences
this immediately after Mechanism 4; schema name is `depth_assignment_schema`; tests are
pytest with a dummy provider; a live sample runner seeds post-Mechanism-4 state and does
not re-call Mechanisms 1–4.

## Explicitly out of scope

- **Mechanism 3 is not implemented.** `interpret` does not insert it between Mechanism 2
  and Mechanism 4. This slice does not read Mechanism 3 output.
- **No `DeepSearchFeature` class.** Only Responsibility 1 exists; `interpret` is the
  coordinator.
- **No metric emission, rationale field, or retrieval.** Maps / web search / firecrawl /
  diffbot are not called.
- **No mix of inferred entries into `resolved_explicit_categories`.**
- **No new LLM provider, persistence, route, or repository.** The handoff stays in-process.

---

# 1. File and Module Structure

Placement follows the live layering already in the service: contracts in `feature_schemas/`,
prompt content in `feature_prompts/`, workflow in `requirement_interpretation.py`, error
semantics in `exceptions/`, tests in `backend/tests/`, dev scripts in `feature_sample_runs/`.
LLM SDKs stay in `clients/`. No new `utils/`, route, repository, or client file. No file
exists per stage — Mechanism 5 extends the same class in the same file as Mechanisms 1, 2,
and 4.

### New files — this slice adds 3 source files

| File | Owns | Contains |
| --- | --- | --- |
| [feature_prompts/depth_assignment_instruction.py](../feature_prompts/depth_assignment_instruction.py) | M5 prompt text | task, scale, floors, triggers, contract, 6 pairs, `build_depth_assignment_instruction` |
| [tests/services/deep_search/test_mechanism_5_depth.py](../../../../tests/services/deep_search/test_mechanism_5_depth.py) | assembled-path fixture set | dummy provider; skip, stamp, reject-body checks |
| [feature_sample_runs/depth_assignment_sample_run.py](../feature_sample_runs/depth_assignment_sample_run.py) | live M5 sample | seeded post-M4 state; stage-by-stage print; one depth call |

### Modified files

| File | Change |
| --- | --- |
| [feature_schemas/schemas.py](../feature_schemas/schemas.py) | `DepthLevel`, `depth` on both store types, wire models, schema name, schema builder |
| [requirement_interpretation.py](../requirement_interpretation.py) | add M5 workflow and stages; rewire `interpret` after Mechanism 4 |
| [exceptions/deep_search.py](../../../exceptions/deep_search.py) | add `DepthAssignmentError` base + provider/validation subclasses with `stage` |

No new composition-root file: `create_requirement_interpretation(settings)` is unchanged.
Existing `ResolvedCategory(...)` / `InferredCategory(...)` call sites stay valid because
`depth` is a trailing default `None`.

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| `DepthCalibrationService` / `Mechanism5` class | methods on `UserRequirementsInterpretation` | locked rule; stages share the responsibility's providers |
| `depth_contracts.py` module | fields in the one `schemas.py` | all service contracts stay in one place, as in M1, M2, and M4 |
| Per-`taxonomy_node` depth table | instruction text | assignment is dynamic LLM judgement from origin plus trigger |
| Fill / drop / clamp missing depths in code | reject the whole body | locked all-or-nothing; code must not invent a depth |
| Merge prompt into `inference_instruction.py` | own `depth_assignment_instruction.py` | depth scale and floors change independently of inference distinctness |
| Generalize `_clarification_coverage_miss` | local id-coverage check in execute | 2B helper logs and names clarification misses |
| `DepthAssignmentInput` record for Operation 1 | instruction function + render helper | M4 pattern; no extra contract |
| `DeepSearchFeature` coordinator class | `interpret` sequences M5 after M4 | only Responsibility 1 exists; Mechanism 3 is out of scope |
| Re-call M1–M4 inside the M5 sample | seeded post-M4 state | earlier mechanisms are already sampled |

---

# 2. Architecture and Modularity Decisions

See [mechanism_5_architecture_decisions.md](mechanism_5_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation — raw input → per-category specification
   ├─ Mechanism 1 Workflow: parse_unstructured_input — unstructured input → extracted buckets
   ├─ Mechanism 2 Workflow: run_explicit_category_resolution — map, maybe clarify, re-resolve
   ├─ Mechanism 4 Workflow: run_persona_driven_category_inference — persona facts → 0..2 inferred nodes
   └─ Mechanism 5 Workflow: run_per_category_depth_calibration — remaining categories → stamped depth
      ├─ (contract) DepthAssignmentResult schema — see §B, not a runtime method
      ├─ Stage: build_depth_assignment_instruction — scale, floors, triggers, contract, six pairs
      ├─ Stage: execute_depth_assignment — one call → valid body or typed error
      ├─ Stage: stamp_category_depths — write depth onto matching entries
      └─ (harness) dummy-provider path checks — test-only, not in request path
```

Empty-list skip lives inside the workflow method, not as its own stage. The schema is a
**contract** (§B). The fixture set is **test-only** and excluded from §E. There is no
`DeepSearchFeature` node because only Responsibility 1 exists.

## B. Data Contracts

All of these live in [feature_schemas/schemas.py](../feature_schemas/schemas.py), except the
error types in [exceptions/deep_search.py](../../../exceptions/deep_search.py).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `DepthLevel` | three-member depth enum | `"basic_profile"` · `"operating_details"` · `"specific_attributes"` | type alias | wire + store |
| `DepthAssignmentEntry` | one wire assignment | `category_id: int` — echoed submitted id · `depth: DepthLevel` | wire model | execute → stamp |
| `DepthAssignmentResult` | batched wire body | `assignments: list[DepthAssignmentEntry]` — length must equal submitted count | wire model | execute → stamp |
| `ResolvedCategory` *(extended)* | stored explicit entry | existing fields plus `depth: DepthLevel \| None = None` | **mutable** — stamp writes `depth` | M2 (`None`) → M5 |
| `InferredCategory` *(extended)* | stored inferred entry | existing fields plus `depth: DepthLevel \| None = None` | **mutable** — stamp writes `depth` | M4 (`None`) → M5 |
| `RequirementInterpretationState` | mutable workflow state | unchanged fields; M5 mutates nested `depth` only | **mutable** | M4 → M5 → later |
| `DepthAssignmentError` | M5 failure base with `stage` | `message: str` · `stage: str` — default `execute_depth_assignment` | immutable | execute → caller |
| `DepthAssignmentProviderError` | no provider returned a body | inherits `DepthAssignmentError` | immutable | execute → caller |
| `DepthAssignmentValidationError` | body failed schema, id set, or explicit floor | inherits `DepthAssignmentError` | immutable | execute → caller |

Rules surfaced here: empty `assignments` is valid only on the skip path (call never sent);
closed schema (`additionalProperties: false`); leftover flags and `user_responses` are not
inputs; no rationale and no metric list on the body;
`DEPTH_ASSIGNMENT_SCHEMA_NAME = "depth_assignment_schema"`.

`depth_assignment_json_schema()` derives from `DepthAssignmentResult`, reuses
`_apply_strict_object_rules`, and does **not** inject the taxonomy enum (the wire has no
`taxonomy_node`).

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol *(reused)* | `generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict [raises: LLMProviderError]` | `OpenAIStructuredProvider`, `GroqStructuredProvider` | execute |
| `depth_assignment_json_schema` | schema derivation | `() -> dict` — strict schema, three-value depth enum | one | instruction, execute |
| `build_depth_assignment_instruction` | function | `(json_schema: dict) -> str` — task, scale, floors, contract, six pairs | one | instruction stage |
| `_call_providers` | helper *(reused)* | `(*, instruction, user_content, json_schema, schema_name, stage, provider_error_cls) -> tuple[dict, str]` | one | execute |

No new provider. Composition root unchanged. Why the protocol is reused lives in the
architecture file.

## D. Class and Method Blueprint

**`UserRequirementsInterpretation`** — in
[requirement_interpretation.py](../requirement_interpretation.py). Mechanism 5 adds the
methods below. Existing M1, M2, and M4 methods stay. The class holds the same injected
`StructuredLLMProvider` chain.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `interpret` | `(raw_input: str) -> RequirementInterpretationState [raises: DepthAssignmentProviderError, DepthAssignmentValidationError]` | sequence parse, M2, M4, then M5 |
| `run_per_category_depth_calibration` | `(state: RequirementInterpretationState) -> RequirementInterpretationState [raises: DepthAssignmentProviderError, DepthAssignmentValidationError] [mutates: each remaining *.depth]` | skip both-empty, else drive instruction → execute → stamp |
| `build_depth_assignment_instruction` | `(json_schema: dict) -> str` | assemble scale, floors, triggers, contract, pairs |
| `execute_depth_assignment` | `(state: RequirementInterpretationState, instruction: str) -> DepthAssignmentResult [raises: DepthAssignmentProviderError, DepthAssignmentValidationError]` | constrained call, then independent body validation |
| `stamp_category_depths` | `(state: RequirementInterpretationState, body: DepthAssignmentResult) -> None [mutates: matching entry.depth]` | write depth onto matching entries by id |

**Module-level functions**

| Function | Module | Signature | Purpose (one line) |
| --- | --- | --- | --- |
| `depth_assignment_json_schema` | `feature_schemas/schemas.py` | `() -> dict` | strict depth schema, three-value enum |
| `build_depth_assignment_instruction` | `feature_prompts/depth_assignment_instruction.py` | `(json_schema: dict) -> str` | depth instruction assembly |
| `_render_depth_assignment_user_content` | `requirement_interpretation.py` | `(state: RequirementInterpretationState) -> str` | JSON dump of payload, persona, origin-labeled rows |
| `_submitted_depth_category_ids` | `requirement_interpretation.py` | `(state: RequirementInterpretationState) -> list[int]` | explicit ids then inferred ids, in list order |
| `_depth_id_coverage_miss` | `requirement_interpretation.py` | `(returned_ids: list[int], submitted_ids: list[int]) -> dict \| None` | missing / extra / duplicate ids, or `None` |
| `_call_providers` *(reused)* | `requirement_interpretation.py` | `(*, instruction, user_content, json_schema, schema_name, stage, provider_error_cls=CategoryMappingProviderError) -> tuple[dict, str] [raises: provider_error_cls]` | try providers in order; raise the given error class |

`interpret` calls `parse_unstructured_input`, then `run_explicit_category_resolution`, then
`run_persona_driven_category_inference`, then `run_per_category_depth_calibration`. It does
not call Mechanism 3.

## E. Runtime Flow — Data Object Journey

Test harness excluded — not in the request path.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `parse_unstructured_input` | `raw_input: str` | state with `extracted` | `resolved=None`, `inferred_categories=[]`, depths unset |
| 2 | `run_explicit_category_resolution` | state (`extracted`) | `state.resolved` | explicit entries exist, `depth=None` |
| 3 | `run_persona_driven_category_inference` | state (`resolved`) | `state.inferred_categories` | inferred entries 0–2, `depth=None` |
| 4 | skip check inside workflow | both category lists | return unchanged if both `[]` | no call; depths stay unset |
| 5 | `build_depth_assignment_instruction` | `depth_assignment_json_schema()` | `instruction: str` | state unchanged |
| 6 | `execute_depth_assignment` | state, instruction, providers | `DepthAssignmentResult` **or** typed error | state unchanged |
| 7 | `stamp_category_depths` | body, existing entries | each matching `*.depth` | every remaining entry has a non-`None` depth |

**Transformation trace (shape only):**

```
RequirementInterpretationState{ payload, extracted, resolved, inferred_categories, *.depth=None }
 → skip: both lists [] → return state
 → (+ depth instruction, + json_schema, + origin-labeled user content)
 → dict                                                                # raw body, local to execute
 → DepthAssignmentResult{ assignments: [{category_id, depth}, ...] }
   | DepthAssignmentProviderError | DepthAssignmentValidationError     # execute exits
 → explicit[].depth in {operating_details, specific_attributes}
   inferred[].depth in {basic_profile, operating_details, specific_attributes}
 → return state
```

**Approach at the real decision points:**

- Skip only when `resolved_explicit_categories` and `inferred_categories` are both empty.
  One non-empty list still runs the call. Thin signals still run the call.
- Providers are tried in the bound order: primary (OpenAI) first; Groq only if the primary
  fails to return a response. Which provider is primary is decided at the composition root,
  not inside this stage (see the architecture file).
- The schema constrains the output at generation time (closed objects, depth enum). The
  first returned body is then validated as an independent second check against
  `DepthAssignmentResult`.
- After schema accept, the `category_id` list must equal the submitted list as a set, with
  the same length (no missing, extra, or duplicate ids). Any miss rejects the whole body.
  Code does not fill a missing id with a floor.
- After id coverage, any assignment whose `category_id` is explicit and whose `depth` is
  `basic_profile` rejects the whole body. Code does not clamp up.
- Two distinct exits, each naming the stage: `DepthAssignmentProviderError` when no
  provider returned a body; `DepthAssignmentValidationError` when the body failed schema,
  id coverage, or the explicit floor.
- User content is a JSON dump of `payload.normalized_text`, `persona_facts`, and one row
  per category: `{category_id, taxonomy_node, origin}` plus `characteristics` (explicit) or
  `reasoning` (inferred). Origin is the literal `explicit` or `inferred`. Leftover flags
  and `user_responses` are omitted.
- Stamp walks accepted assignments. Explicit ids update the matching `ResolvedCategory`.
  Inferred ids update the matching `InferredCategory`. `taxonomy_node`, `characteristics`,
  `reasoning`, `raw_name`, `provenance`, `persona_facts`, `payload`, `extracted`, and
  `user_responses` stay unchanged. Lists are not replaced.

## F. Method Detail

**`run_per_category_depth_calibration`**

- **Purpose:** skip when there is nothing to assign, otherwise sequence instruction, call,
  and stamp.
- **What it does:** require `state.resolved`; if both category lists are empty, log a skip
  event and return; else build instruction, execute, stamp, return the same state.
- **Inputs:** state after Mechanism 4 · **Outputs:** same state · **Failure:** execute typed
  errors. Skip is not a failure.

**`build_depth_assignment_instruction`**

- **Purpose:** make one call return exactly one depth per submitted id, from origin floor
  plus trigger.
- **What it does:** concatenate task statement; three-level scale (question, contents,
  tools, contract-gated); origin floors and escalation; movement rule (start at floor,
  escalate only on a trigger); acceptance test; metric contract (do not emit metrics);
  signal sources (`payload`, `characteristics` for explicit, `reasoning` for inferred,
  `persona_facts`); origin is labeled, not inferred from the node; negative rules (do not
  invent/drop categories, do not emit metrics, do not assign `basic_profile` to explicit,
  echo `category_id`); closed schema; six worked pairs on nodes that the sample runner will
  not reuse: (1) explicit, no trigger → `operating_details`; (2) explicit, named attribute
  the floor cannot answer → `specific_attributes`; (3) inferred, no attribute signal →
  `basic_profile`; (4) inferred, operational/quality signal → `operating_details`;
  (5) inferred, narrow user-specific signal → `specific_attributes`; (6) mixed batch, one
  of each origin, floors held where no trigger.
- **Inputs:** `json_schema` · **Outputs:** `str` · **Failure:** none.

**`execute_depth_assignment`**

- **Purpose:** return a schema-valid, id-complete, floor-legal body, or a typed failure.
- **What it does:** take user content from `_render_depth_assignment_user_content`; send
  instruction as the system message; try providers in the bound order; validate the first
  body against `DepthAssignmentResult`; schema failure rejects with no retry; then reject
  if ids miss/extra/duplicate versus `_submitted_depth_category_ids`; then reject if any
  explicit id is `basic_profile`; do not stamp; do not clamp; do not fill.
- **Inputs:** `state`, `instruction` · **Outputs:** `DepthAssignmentResult` · **Failure:**
  `DepthAssignmentProviderError` (no provider answered), `DepthAssignmentValidationError`
  (schema, id coverage, or explicit floor).

**`stamp_category_depths`**

- **Purpose:** write accepted depths onto the existing entries.
- **What it does:** index explicit and inferred entries by `category_id`; for each
  assignment, set `.depth` on the matching object; leave every other field and every other
  state field untouched; log stamped counts by origin.
- **Inputs:** `state`, `body` · **Outputs:** none · **Failure:** none (execute already
  guaranteed coverage).

---

# 4. Sample Runner and Dummy-Provider Fixture Set

Neither check is part of the request path in §E. No new settings.

## 4.1 Live sample runner

From `backend/`:

`python -m src.services.deep_search.feature_sample_runs.depth_assignment_sample_run`

It seeds a Mechanism-4-style `RequirementInterpretationState` (`state.resolved` set;
`inferred_categories` already written; every `depth` is `None`). Explicit nodes:
`sports_complex` with beginner-class / auto-belay characteristics, `farmers_market` with an
empty characteristic list. Inferred: `veterinary_care` (id after extracted max) with
reasoning about a newly adopted cat that still needs vaccinations. Payload: a couple
moving near a canal, one climbs indoors, they shop outdoor markets, night-shift nurse,
rescue cat. The seed does not reuse the depth few-shot inputs (gym, supermarket, child_care_agency,
pharmacy, park, cafe). Mechanisms 1–4 are not called. One live depth call.

It builds the responsibility through `create_requirement_interpretation(get_settings())`,
then calls the Mechanism 5 stage methods in sequence rather than
`run_per_category_depth_calibration`, printing a titled section after each:

| Section printed | Content |
| --- | --- |
| `INPUT STATE` | seeded payload, extracted, resolved, inferred; every `depth` starts `None` |
| `STAGE - SCHEMA` | `depth_assignment_json_schema()`; depth enum; no metric fields |
| `STAGE - INSTRUCTION` | depth instruction in full; few-shot count |
| `STAGE - USER CONTENT` | JSON dump with origin labels |
| `STAGE - PROVIDER ATTEMPTS` | one line per attempt; then the raw decoded body |
| `STAGE - VALIDATED` | `DepthAssignmentResult` via `model_dump_json(indent=2)` |
| `STAGE - STAMPED DEPTHS` | each explicit and inferred row with `depth` written |
| `STAGE - UNCHANGED FIELDS` | node / characteristics / reasoning / persona snapshot equality |

Execute discards the raw body once the typed contract exists, so the runner attaches a
collecting log handler and reads attempt lines and the raw body off
`DEEP_SEARCH_LOGGER_NAME` (`category_resolution.*` events, filtered by
`execute_depth_assignment`). On a typed failure it catches `DepthAssignmentError`, prints
the class, its `stage`, and the message, and exits non-zero. Nothing written to disk.

## 4.2 Dummy-provider fixture set

The pytest file is a dev check. No real provider calls. Dummy provider pattern matches
[test_mechanism_4_inference.py](../../../../tests/services/deep_search/test_mechanism_4_inference.py).
State is seeded as after Mechanism 4 (`resolved` set, `inferred_categories` written,
`depth=None`).

From `backend/`:

`pytest tests/services/deep_search/test_mechanism_5_depth.py`

It constructs `UserRequirementsInterpretation` with a fake `StructuredLLMProvider` whose
`generate_structured` returns a recorded dict. It runs the real skip, validate, floor, and
stamp path.

| Check | Asserts |
| --- | --- |
| both lists empty | no provider call; lists stay `[]`; no exception |
| explicit only, legal depths | each explicit `depth` stamped; inferred stays `[]` |
| inferred only, `basic_profile` | inferred depth stamped; explicit stays `[]` |
| mixed batch, floors and one escalation | matching depths on the right objects; other fields unchanged |
| explicit assigned `basic_profile` | `DepthAssignmentValidationError`; all depths stay `None` |
| missing id / extra id / duplicate id | validation error; no stamp |
| illegal depth string | validation error |
| empty signals still call | provider was called; floors stamped |
| instruction-only trigger judgement | dummy body already obeys; code did not rewrite a valid escalation |

Existing M2/M4 tests do not need edits: `depth=None` is a trailing default.

---

# 5. Async Structure

The stack is already async down to `generate_structured`
([async_conversion_implementation_plan.md](async_conversion_implementation_plan.md)).
Mechanism 5 adds one awaited I/O point on that chain.

| Layer | Operations and I/O | Data dependency | Execution mode | Blocking check |
| --- | --- | --- | --- | --- |
| `interpret` | await M1, M2, M4, M5 | data-dependent; each writes state the next reads | sequential await; no `gather` | none new |
| `run_per_category_depth_calibration` | empty-list check; instruction (CPU); await execute (HTTP); stamp (memory) | stamp needs the accepted body; skip needs both lists | sequential; skip returns before any await | instruction concat stays on the event-loop thread; not offloaded |
| `execute_depth_assignment` | await `_call_providers`; Pydantic; id coverage; explicit-floor check | validation needs the returned body | sequential await, then sync checks | Pydantic and set compares are short CPU; not offloaded |
| `_call_providers` *(reused)* | await `generate_structured` per bound provider until one body returns | fallback needs the primary to fail first | sequential await; primary then Groq; no `gather` | HTTP is already async on `AsyncOpenAI` / `AsyncGroq` |

Shared-state handling: not concurrent. Stamp runs after the await completes. M5 does not
introduce a worker, a new event-loop policy, or concurrent mutation of
`RequirementInterpretationState`.
