# Deep Search: Mechanism 6 Implementation Plan

Mechanism 6 of the **User Requirement Interpretation** responsibility: after Mechanism 5 has
stamped `depth` on every category, one batched constrained LLM call defines the dynamic
metrics each eligible category's depth allows. Code drops any metric that fails the contract
rules K1 to K6, reports categories left short, and writes one `CategoryMetricSet` per
category to a new `state.category_metrics` list. It does not fetch, does not assign depth,
and does not touch the category objects. Metric definition is methods on the existing
responsibility class. No new class layer. Mechanism 3 stays excluded.

Architecture decisions: `mechanism_6_architecture_decisions.md`.

Locked decisions (from the Mechanism 6 spec in `deep_search_context.md`):

- Input is the `RequirementInterpretationState` after Mechanism 5. `depth` is set on every category.
- Eligible category: `depth` is `operating_details` or `specific_attributes`. `basic_profile` is never sent.
- Both lists empty: no call, `category_metrics` stays `[]`. All `basic_profile`: no call, one set per category with `metrics = None`. Neither fails.
- At least one eligible category: one batched call. Thin or empty signals do not skip.
- No predefined per-category or per-group metric list in code. Worked examples only.
- Schema miss or id-set mismatch rejects the whole body. A metric that fails K1 to K6 is dropped and logged. Code never repairs a metric.
- Metrics live in a separate `state.category_metrics` list. `ResolvedCategory` and `InferredCategory` are unchanged. No facts list.
- Fixed dimensions are a code constant by depth. They are not model output and are not stored on the state.
- Tools: `google_maps`, `parallel_web_search`, `firecrawl`. Diffbot is not used.
- Caps: at most 4 metrics per band per category. Minimum per band is a logged shortfall, not a failure.
- Schema name `metric_definition_schema`. Stage name `execute_metric_definition`.
- Sample runner seeds post-Mechanism-5 state and does not re-call Mechanisms 1 to 5.

## Explicitly out of scope

- **Mechanism 3 and Mechanism 7.** `interpret` does not call Mechanism 3. Nothing here reads or shapes Mechanism 7.
- **No `DeepSearchFeature` class.** Only Responsibility 1 exists, and `interpret` is the coordinator, as in Mechanism 5.
- **No retrieval.** Maps, parallel web search, and firecrawl are named in `resolution_source` only. They are not called.
- **No new provider, persistence, route, repository, or settings.**
- **No edit to the Mechanism 5 spec markdown.** The `DEPTH_SCALE` prompt text is synced in one small edit (see checklist item 5).

---

# 1. File and Module Structure

Placement follows the live layering: contracts in `feature_schemas/`, prompt text in
`feature_prompts/`, workflow in `requirement_interpretation.py`, error types in
`exceptions/`, tests in `backend/tests/`, dev scripts in `feature_sample_runs/`. No file per
stage. Mechanism 6 extends the same class in the same file as Mechanisms 1, 2, 4, and 5.

### New files (3)

| File | Owns | Contains |
| --- | --- | --- |
| `feature_prompts/metric_definition_instruction.py` | M6 prompt text | task, bands, contract, fixed-dimension list, tie rules, negatives, worked pairs, `build_metric_definition_instruction` |
| `tests/services/deep_search/test_mechanism_6_metrics.py` | assembled-path fixture set | fake provider; skip, schema, id set, K1 to K6, shortfall, write-shape checks |
| `feature_sample_runs/metric_definition_sample_run.py` | live M6 sample | seeded post-M5 state; stage-by-stage print; one metric-definition call |

### Modified files

| File | Change |
| --- | --- |
| `feature_schemas/schemas.py` | value aliases, wire models, store dataclasses, `category_metrics` on the state, fixed-dimension constant, cap, schema name, schema builder |
| `requirement_interpretation.py` | add the M6 workflow and stage methods, module helpers, and rewire `interpret` after Mechanism 5 |
| `exceptions/deep_search.py` | add `MetricDefinitionError` base plus provider and validation subclasses |
| `feature_prompts/depth_assignment_instruction.py` | text-only sync of `DEPTH_SCALE`: website moves to `basic_profile`, firecrawl replaces "firecrawl/diffbot" |

No new composition-root file. `create_requirement_interpretation(settings)` is unchanged.
Existing `RequirementInterpretationState(...)` call sites stay valid because
`category_metrics` has a default empty list.

### What was collapsed and why

| Was going to be | Now | Reason |
| --- | --- | --- |
| `MetricDefinitionService` class | methods on `UserRequirementsInterpretation` | locked rule; stages share the providers and state |
| `metric_contracts.py` module | fields in the one `schemas.py` | all service contracts stay in one place |
| `metric_rules.py` with a rule class per K rule | one `apply_metric_contract` method plus one small rule helper | six checks on one dataclass; no second consumer |
| Rejection-record dataclass | plain dict in the log record and return value | read only by the log and the runner |
| Per-`taxonomy_node` metric catalog | instruction text and worked pairs | locked: LLM defines metrics each run |
| Fixed-dimension constant in its own module | constant beside `DepthLevel` in `schemas.py` | read by the instruction module and later stages; one owner |
| Generalize `_depth_id_coverage_miss` | reuse it as-is | signature is already `(returned_ids, submitted_ids)` |
| Re-call M1 to M5 in the sample runner | seeded post-M5 state | earlier mechanisms are already sampled |

---

# 2. Architecture and Modularity Decisions

See [mechanism_6_architecture_decisions.md](mechanism_6_architecture_decisions.md).

---

# 3. Code-Level Structure and Workflow Blueprint

## A. Feature Map

```
Feature: Deep Search / Neighborhood Quality
└─ Responsibility: UserRequirementsInterpretation: raw input to per-category specification
   ├─ Mechanism 1 Workflow: parse_unstructured_input
   ├─ Mechanism 2 Workflow: run_explicit_category_resolution
   ├─ Mechanism 4 Workflow: run_persona_driven_category_inference
   ├─ Mechanism 5 Workflow: run_per_category_depth_calibration
   └─ Mechanism 6 Workflow: run_per_category_metric_definition: eligible categories to metric sets
      ├─ (contract) MetricDefinitionResult schema: see B, not a runtime method
      ├─ Stage: build_metric_definition_instruction: bands, contract, rules, worked pairs
      ├─ Stage: execute_metric_definition: one call, then schema and id-set checks
      ├─ Stage: apply_metric_contract: rules K1 to K6, drop failing metrics
      ├─ Stage: report_metric_shortfalls: log eligible categories with an empty band
      ├─ Stage: write_category_metrics: one CategoryMetricSet per category into state
      └─ (harness) dummy-provider path checks: test-only, not in request path
```

The skip branch lives inside the workflow method. The schema is a contract (B). The fixture
set is test-only and excluded from E. There is no `DeepSearchFeature` node because only
Responsibility 1 exists.

## B. Data Contracts

All in `feature_schemas/schemas.py` except the error types in `exceptions/deep_search.py`.

| Contract | Purpose | Fields (`name: type, meaning`) | Mutability | Created by, read by |
| --- | --- | --- | --- | --- |
| `MetricValueType` | value type alias | `number_with_unit`, `boolean`, `enum`, `date_time` | type alias | wire + store |
| `NullPolicy` | unresolved-value alias | `null`, `unknown` | type alias | wire + store |
| `ResolutionTool` | tool alias | `google_maps`, `parallel_web_search`, `firecrawl` | type alias | wire + store |
| `MetricBand` | band alias | `operating_details`, `specific_attributes` | type alias | wire + store |
| `ResolutionSourceEntry` | wire tool and target | `tool: ResolutionTool` · `target: str` | wire model | execute, apply |
| `MetricEntry` | one wire metric | `label`, `question`, `verification`: `str` · `value_type: MetricValueType` · `unit: str \| None` · `enum_values: list[str]` · `resolution_source: ResolutionSourceEntry` · `null_policy: NullPolicy` · `band: MetricBand` | wire model | execute, apply |
| `CategoryMetricsEntry` | wire metrics per category | `category_id: int` (echoed) · `metrics: list[MetricEntry]` (may be empty) | wire model | execute, apply |
| `MetricDefinitionResult` | batched wire body | `categories: list[CategoryMetricsEntry]` | wire model | execute, apply |
| `ResolutionSource` | stored tool and target | `tool: ResolutionTool` · `target: str` | dataclass | apply, write |
| `MetricSpec` | one stored metric | same fields as `MetricEntry`, with `resolution_source: ResolutionSource`, text trimmed | dataclass | apply, write |
| `CategoryMetricSet` | metrics for one category | `category_id: int` · `taxonomy_node: str` (copied by code) · `metrics: list[MetricSpec] \| None` | **mutable list on state** | write, later stages |
| `RequirementInterpretationState` *(extended)* | mutable workflow state | existing fields plus `category_metrics: list[CategoryMetricSet]` (default `[]`) | **mutable** | M5 to M6 to later |
| `FIXED_DIMENSIONS_BY_DEPTH` | fixed dimensions by depth | `DepthLevel` to `tuple[str, ...]`, cumulative | constant | instruction, later stages |
| `MAX_METRICS_PER_BAND` | cap | `4` | constant | apply, instruction |
| `MetricDefinitionError` | M6 failure base with `stage` | `message: str` · `stage: str` (default `execute_metric_definition`) | immutable | execute to caller |
| `MetricDefinitionProviderError` | no provider returned a body | inherits base | immutable | execute to caller |
| `MetricDefinitionValidationError` | body failed schema or id set | inherits base | immutable | execute to caller |

Rules surfaced here:
- `metrics = None` means "not eligible (`basic_profile`)". `metrics = []` means "eligible, nothing survived".
- The schema is closed (`additionalProperties: false`, every property required). It carries types and closed enums only. It carries no `minLength`, `maxLength`, `minItems`, `maxItems`, or conditional keywords, because Groq strict mode does not support them.
- `unit` is nullable. `enum_values` is a list that is empty when unused.
- `taxonomy_node` and `depth` are not on the wire body.
- `METRIC_DEFINITION_SCHEMA_NAME = "metric_definition_schema"`.
- Fixed dimensions: `basic_profile` = name, category, address, website, `place_id`, coords, travel distance and duration per mode (walk, drive, transit, cycle), reachability. `operating_details` = those plus hours, contact (phone), rating, review volume, price level. `specific_attributes` = same as `operating_details`.

`metric_definition_json_schema()` derives from `MetricDefinitionResult` and reuses
`_apply_strict_object_rules`. It does not inject the taxonomy enum.

## C. Supporting Actors and Interfaces

| Actor | Kind | Contract (methods) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMProvider` | protocol *(reused)* | `generate_structured(*, instruction, user_content, json_schema, schema_name) -> dict [raises: LLMProviderError]` | `OpenAIStructuredProvider`, `GroqStructuredProvider` | execute |
| `metric_definition_json_schema` | schema derivation | `() -> dict`: strict schema, closed enums | one | instruction, execute |
| `build_metric_definition_instruction` | function | `(json_schema: dict) -> str` | one | instruction stage |
| `_call_providers` | helper *(reused)* | `(*, instruction, user_content, json_schema, schema_name, stage, provider_error_cls) -> tuple[dict, str]` | one | execute |
| `_depth_id_coverage_miss` | helper *(reused)* | `(returned_ids: list[int], submitted_ids: list[int]) -> dict \| None` | one | execute |

No new provider. Composition root unchanged.

## D. Class and Method Blueprint

**`UserRequirementsInterpretation`** in `requirement_interpretation.py`. Mechanism 6 adds
the methods below. Existing M1, M2, M4, and M5 methods stay. The class holds the same
injected provider chain.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `interpret` | `(raw_input: str) -> RequirementInterpretationState [raises: MetricDefinitionProviderError, MetricDefinitionValidationError]` | sequence parse, M2, M4, M5, then M6 |
| `run_per_category_metric_definition` | `(state: RequirementInterpretationState) -> RequirementInterpretationState [raises: MetricDefinitionProviderError, MetricDefinitionValidationError] [mutates: state.category_metrics]` | skip when nothing eligible, else instruction, execute, filter, write |
| `build_metric_definition_instruction` | `(json_schema: dict) -> str` | assemble bands, contract, rules, pairs |
| `execute_metric_definition` | `(state: RequirementInterpretationState, instruction: str) -> MetricDefinitionResult [raises: MetricDefinitionProviderError, MetricDefinitionValidationError]` | one call, then schema and id-set checks |
| `apply_metric_contract` | `(state: RequirementInterpretationState, body: MetricDefinitionResult) -> tuple[dict[int, list[MetricSpec]], list[dict]]` | drop metrics failing K1 to K6; return survivors and rejections |
| `report_metric_shortfalls` | `(state: RequirementInterpretationState, survivors: dict[int, list[MetricSpec]]) -> list[dict]` | log eligible categories with an empty required band |
| `write_category_metrics` | `(state: RequirementInterpretationState, survivors: dict[int, list[MetricSpec]]) -> None [mutates: state.category_metrics]` | build one set per category, explicit then inferred |

**Module-level functions**

| Function | Module | Signature | Purpose (one line) |
| --- | --- | --- | --- |
| `metric_definition_json_schema` | `feature_schemas/schemas.py` | `() -> dict` | strict metric-definition schema |
| `build_metric_definition_instruction` | `feature_prompts/metric_definition_instruction.py` | `(json_schema: dict) -> str` | instruction assembly |
| `build_metric_definition_few_shot_examples` | `feature_prompts/metric_definition_instruction.py` | `() -> tuple[tuple[str, str], ...]` | worked pairs as JSON text, read by the runner |
| `_ordered_categories` | `requirement_interpretation.py` | `(state) -> list[ResolvedCategory \| InferredCategory]` | explicit entries then inferred, list order |
| `_is_metric_eligible` | `requirement_interpretation.py` | `(category) -> bool` | true when depth is operating_details or specific_attributes |
| `_render_metric_definition_user_content` | `requirement_interpretation.py` | `(state) -> str` | JSON of payload, persona, eligible rows, leftover flags |
| `_metric_rule_failure` | `requirement_interpretation.py` | `(entry: MetricEntry, depth: DepthLevel) -> str \| None` | first failed rule of K1 to K4, else `None` |
| `_to_metric_spec` | `requirement_interpretation.py` | `(entry: MetricEntry) -> MetricSpec` | wire metric to stored metric, text trimmed |
| `_call_providers`, `_depth_id_coverage_miss`, `_timestamp` *(reused)* | `requirement_interpretation.py` | unchanged | provider loop, id check, log time |

`interpret` calls `parse_unstructured_input`, `run_explicit_category_resolution`,
`run_persona_driven_category_inference`, `run_per_category_depth_calibration`, then
`run_per_category_metric_definition`. It does not call Mechanism 3.

## E. Runtime Flow: Data Object Journey

Test harness excluded. Not in the request path.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `run_per_category_depth_calibration` (M5) | state | `*.depth` on every category | `category_metrics = []` |
| 2 | skip check in workflow | both lists, each `depth` | both empty: `category_metrics` stays `[]`, return | no call |
| 3 | skip check in workflow | each `depth` | none eligible: `write_category_metrics` with no survivors | one set per category, `metrics = None` |
| 4 | `build_metric_definition_instruction` | `metric_definition_json_schema()`, `FIXED_DIMENSIONS_BY_DEPTH` | `instruction: str` | state unchanged |
| 5 | `execute_metric_definition` | state, instruction, providers | `MetricDefinitionResult` **or** typed error | state unchanged |
| 6 | `apply_metric_contract` | state, body | survivors by id, rejection records, log events | state unchanged |
| 7 | `report_metric_shortfalls` | state, survivors | log events, list of short categories | state unchanged |
| 8 | `write_category_metrics` | state, survivors | `state.category_metrics` | one set per category |

**Transformation trace (shape only):**

```
RequirementInterpretationState{ payload, extracted, resolved, inferred_categories, *.depth set, category_metrics=[] }
 → skip: both lists [] → return state (category_metrics [])
 → skip: no eligible category → category_metrics = [CategoryMetricSet{id, node, metrics=None}, ...]
 → (+ instruction, + json_schema, + user content: eligible rows only)
 → dict                                                        # raw body, local to execute
 → MetricDefinitionResult{ categories: [{category_id, metrics:[MetricEntry...]}] }
   | MetricDefinitionProviderError | MetricDefinitionValidationError   # execute exits
 → survivors{ category_id: [MetricSpec...] } + rejections[{category_id, label, rule}]
 → category_metrics = [CategoryMetricSet{id, node, metrics=[MetricSpec...] | [] | None}, ...]
 → return state
```

**Approach at the real decision points:**

- Skip only when nothing is eligible. One eligible category runs the call, even with empty `persona_facts`, `characteristics`, and leftover flags.
- Providers are tried in the bound order. Groq answers only if the primary fails to return a body. Which provider is primary is decided at the composition root.
- The schema constrains output at generation time (closed objects, closed enums). The first returned body is then validated against `MetricDefinitionResult` as a second check. A schema miss rejects the whole body with no retry.
- After schema accept, the returned `category_id` list must equal the eligible id list with no missing, extra, or duplicate ids. A miss rejects the whole body.
- Rules run per metric in model order, K1 to K6. The first failing rule drops the metric. K5 compares the label with labels already kept for that category. K6 counts kept metrics in that band and drops the fifth.
- K3 reads the category's `depth` by `category_id`. A `specific_attributes` band on an `operating_details` category is dropped.
- A rule failure never raises. It writes a `metric_definition.metric_rejected` log record and adds one entry to the returned rejections.
- Shortfall: an `operating_details` category with zero `operating_details` survivors, or a `specific_attributes` category with zero in either band, is reported. It is not a failure.
- Write assigns a fresh list. Categories are walked explicit then inferred. Eligible categories get their survivors (possibly `[]`). Others get `None`. `taxonomy_node` is copied from the category by `category_id`.
- Two exits, each naming the stage: `MetricDefinitionProviderError` (no provider returned a body) and `MetricDefinitionValidationError` (schema or id set failed).
- User content is a JSON dump of `payload.normalized_text`, `persona_facts`, eligible rows (`category_id`, `taxonomy_node`, `origin`, `depth`, plus `characteristics` for explicit or `reasoning` for inferred), and a `leftover_flags` list of characteristic and persona flags. `basic_profile` rows and `user_responses` are omitted.

## F. Method Detail

**`run_per_category_metric_definition`**

- **Purpose:** skip when nothing is eligible, otherwise sequence the five stages.
- **What it does:** require `state.resolved`; if there are no categories, log a skip and leave `category_metrics` empty; if none are eligible, log a skip and write `None` sets; else build the instruction, await execute, apply the contract, report shortfalls, write, return the same state.
- **Inputs:** state after Mechanism 5 · **Outputs:** same state · **Failure:** execute typed errors. Skip is not a failure.

**`build_metric_definition_instruction`**

- **Purpose:** make one call return contract-passing metrics per eligible category, within each category's depth.
- **What it does:** concatenate task statement; band rule and tool limits (`google_maps`, `parallel_web_search` for `operating_details`; `parallel_web_search`, `firecrawl` for `specific_attributes`); the typed contract fields and the `cozy` rejection with its `ambiance` reformulation; the fixed-dimension list rendered from `FIXED_DIMENSIONS_BY_DEPTH["specific_attributes"]` as "do not propose these"; the tie rule per band; the decision test; the leftover-flag rule; the cap from `MAX_METRICS_PER_BAND`; negative rules; the closed schema; worked pairs on nodes the sample runner will not reuse: (1) explicit `operating_details`, no trigger; (2) explicit `specific_attributes` with a named attribute, both bands; (3) inferred `operating_details`; (4) mixed batch with a leftover flag read into one metric's `question`.
- **Inputs:** `json_schema` · **Outputs:** `str` · **Failure:** none.

**`execute_metric_definition`**

- **Purpose:** return a schema-valid, id-complete body, or a typed failure.
- **What it does:** render user content; send the instruction as the system message; try providers in the bound order; validate the first body against `MetricDefinitionResult`; on schema failure log and raise; compare ids with `_depth_id_coverage_miss` against the eligible ids; on a miss log and raise; log an accepted verdict with the metric count.
- **Inputs:** `state`, `instruction` · **Outputs:** `MetricDefinitionResult` · **Failure:** `MetricDefinitionProviderError`, `MetricDefinitionValidationError`.

**`apply_metric_contract`**

- **Purpose:** keep only metrics that pass K1 to K6, without repairing any.
- **What it does:** map `category_id` to `depth`; for each returned category and each metric in order, take the first failure from `_metric_rule_failure` (K1 blank text, K2 value-type parameters, K3 band above depth, K4 `firecrawl` on the `operating_details` band), then K5 duplicate label, then K6 band cap; log and record each rejection; convert survivors with `_to_metric_spec`.
- **Inputs:** `state`, `body` · **Outputs:** survivors by id (every submitted id present, possibly `[]`) and rejection records · **Failure:** none.

**`report_metric_shortfalls`**

- **Purpose:** make a category left without a required band visible in the log.
- **What it does:** for each eligible category, list which required bands have no survivor; log one `metric_definition.category_underspecified` event per short category; return the same records.
- **Inputs:** `state`, `survivors` · **Outputs:** list of dicts · **Failure:** none.

**`write_category_metrics`**

- **Purpose:** record the result in the state object later stages read.
- **What it does:** walk explicit then inferred categories; build a `CategoryMetricSet` with the copied `taxonomy_node` and either the survivors or `None`; assign the list to `state.category_metrics`; log counts.
- **Inputs:** `state`, `survivors` · **Outputs:** none · **Failure:** none.

---

# 4. Sample Runner and Dummy-Provider Fixture Set

Neither check is part of the request path in E. No new settings.

## 4.1 Live sample runner

From `backend/`:

`python -m src.services.deep_search.feature_sample_runs.metric_definition_sample_run`

It seeds a Mechanism-5-style `RequirementInterpretationState`: `state.resolved` set,
`inferred_categories` written, every `depth` stamped, `category_metrics` empty. Seed:
explicit `swimming_pool` (`specific_attributes`, characteristics about lap lanes open
before 6am and a cool water temperature), explicit `bakery` (`operating_details`, empty
characteristics), inferred `dog_park` (`operating_details`, reasoning about a newly
adopted dog that needs off-leash time), inferred `library` (`basic_profile`, reasoning
about a student in the household). One leftover characteristic flag ("not too crowded" on
the pool). Payload is new wording. The seed does not reuse the worked-pair nodes or
wording (restaurant, gym, pharmacy, daycare). Mechanisms 1 to 5 are not called. One live
metric-definition call.

It builds the responsibility through `create_requirement_interpretation(get_settings())`,
then calls the stage methods in sequence, not `run_per_category_metric_definition`,
printing a titled section after each:

| Section printed | Content |
| --- | --- |
| `INPUT STATE` | seeded payload, categories with depths, leftover flag; `category_metrics` starts empty |
| `STAGE - SCHEMA` | `metric_definition_json_schema()`; closed enums; check that no `minLength` or `maxItems` key appears |
| `STAGE - FIXED DIMENSIONS` | `FIXED_DIMENSIONS_BY_DEPTH` by depth |
| `STAGE - INSTRUCTION` | instruction in full; character count; few-shot pair count |
| `STAGE - USER CONTENT` | JSON dump: eligible rows only, plus leftover flags |
| `STAGE - PROVIDER ATTEMPTS` | one line per attempt; then the raw decoded body |
| `STAGE - VALIDATED` | `MetricDefinitionResult` via `model_dump_json(indent=2)`; metric counts per category |
| `STAGE - CONTRACT FILTER` | survivors by category; each rejection with its rule |
| `STAGE - SHORTFALLS` | categories with an empty required band |
| `STAGE - WRITTEN METRIC SETS` | each `CategoryMetricSet`; `None` for `library` |
| `STAGE - UNCHANGED FIELDS` | category, persona, payload snapshot equality before and after |

The raw body is dropped inside execute, so the runner attaches a collecting log handler
and reads attempt lines and the raw body off `DEEP_SEARCH_LOGGER_NAME`, filtered by
`execute_metric_definition`. On a typed failure it catches `MetricDefinitionError`, prints
the class, `stage`, and message, and exits non-zero. Nothing is written to disk.

## 4.2 Dummy-provider fixture set

From `backend/`:

`pytest tests/services/deep_search/test_mechanism_6_metrics.py`

A fake `StructuredLLMProvider` returns a recorded dict. The real skip, validate, filter,
shortfall, and write path runs. State is seeded after Mechanism 5. Tests are async, the
fake is defined in the file (as in `test_mechanism_5_depth.py`), and log events are read
with `caplog`.

| Check | Asserts |
| --- | --- |
| both lists empty | no provider call; `category_metrics == []`; no exception |
| all `basic_profile` | no provider call; one set per category; every `metrics is None` |
| schema miss: missing field | `MetricDefinitionValidationError`; `category_metrics` stays `[]` |
| schema miss: value outside a closed set | validation error; no write |
| missing / extra / duplicate id | validation error; no write |
| provider chain fails | `MetricDefinitionProviderError` |
| valid mixed batch | sets on the right ids; `taxonomy_node` copied for explicit and inferred; `None` for `basic_profile` |
| K1 blank text | bad metric dropped, neighbor kept; rejection record has rule |
| K2 missing `unit`; enum with one value | each dropped, neighbor kept |
| K3 `specific_attributes` band on an `operating_details` category | dropped |
| K4 `firecrawl` on an `operating_details` metric | dropped |
| K5 repeated label (case-insensitive) | later one dropped |
| K6 fifth metric in one band | fifth dropped, first four kept in order |
| shortfall | eligible category left empty: `category_underspecified` logged, `metrics == []`, no error |
| user content | only eligible rows; each row carries origin and depth; leftover flags present |
| unchanged state | categories, payload, persona, extracted, `user_responses`, `ambiguity_flags`, passes equal before and after |
| instruction-only rules | fixtures obey them; code does not rewrite a valid metric |

Existing M2, M4, and M5 tests need no edits: `category_metrics` has a default.

---

# 5. Async Structure

The stack is already async down to `generate_structured`. Mechanism 6 adds one awaited I/O
point (the call) and one awaited workflow method on that chain.

| Layer | Operations and I/O | Data dependency | Execution mode | Blocking check |
| --- | --- | --- | --- | --- |
| `interpret` | await M1, M2, M4, M5, M6 | data-dependent; each writes state the next reads | sequential await; no `gather` | none new |
| `run_per_category_metric_definition` | eligibility check (memory); instruction (CPU); await execute (HTTP); filter, report, write (memory) | filter needs the accepted body; skip needs each `depth` | sequential; skip returns before any await | instruction build and filters are short CPU on the event-loop thread; not offloaded |
| `execute_metric_definition` | await `_call_providers`; Pydantic validation; id compare | validation needs the returned body | sequential await, then sync checks | Pydantic and set compares are short CPU; not offloaded |
| `_call_providers` *(reused)* | await `generate_structured` per bound provider until one body returns | fallback needs the primary to fail first | sequential await; primary then Groq; no `gather` | HTTP is async on `AsyncOpenAI` / `AsyncGroq` |

Shared-state handling: not concurrent. `category_metrics` is written after the await
completes. Mechanism 6 adds no worker, no new event-loop policy, and no concurrent mutation
of `RequirementInterpretationState`. The sample runner uses `asyncio.run` and awaits
`aclose()` in `finally`.
