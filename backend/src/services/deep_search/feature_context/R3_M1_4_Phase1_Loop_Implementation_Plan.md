# R3.M1.4 Step 1: Phase-1 Loop Implementation Plan

## Context

`run_specific_metric_resolution` is built through STEP 3 (R3.M1.3 discovery). This plan adds STEP 4 for **phase 1 only**: per amenity, a tool-calling loop (function-calling loop) that runs one `web_search` per metric in turn 1, then at most one retry turn for metrics whose search `failed`, and records web evidence into `metrics_source_content`. Triage, phase 2 and resolution are not built, so STEP 4's pipeline is `phase1_loop` alone and its output lands in a temporary state store.

Grounding: spec R3.M1.4 (lines 524-590) and step "1. Phase-1 Loop" (lines 596-684, incl. its `failure_class` prerequisite); R3.M1.5 breaker and pipeline rules (lines 865-879); traceflow Part 3 STEP 4.

Scope decisions confirmed with you:
- **Breaker**: build the run-scoped breaker now, wired into discovery and phase 1.
- **Output**: temporary state store `state.phase1_results`, written once after the STEP 4 barrier.
- **Failure class**: every SDK/API exception (timeout, 429, 5xx, connection, 401/403, 400, other API errors) is `availability`; refusal, abnormal or truncated `finish_reason`, empty/non-JSON body, empty tool turn are `content`.
- **Prerequisites included**: per-kind gateway retry limits, `failure_class` → `cause`, R3.M1.1 steps 3-5, R3.M1.2 shaping (web_search scope).
- **Sample runner**: the existing `r3_m1_3_website_url_discovery_sample_run.py` is extended (your instruction overrides the "new file" default in Plan_output_format).

---

## Build checklist (todos, in order)

1. `mcp_tools.py`: per-kind retry limits (`(2.0,)` / `(30.0, 30.0)`); update gateway tests.
2. `exceptions/llm.py` + `llm_provider.py`: `failure_class` on every `LLMProviderError` raise site.
3. `exceptions/deep_search.py` + `llm_provider.py`: required `cause` on `MetricResolutionProviderError`; chain aggregation in `call_turn` / `call_structured`.
4. `phase_tool_catalog.py`: R3.M1.1 steps 3-5 (`build_rejection_outcomes`, `sanitize_replay_message`, `prepare_admitted_calls`).
5. `schemas.py`: phase-1 contracts + `MetricsSourceContent` store + `state.phase1_results`.
6. `core/config.py`: `METRIC_RESOLUTION_BREAKER_THRESHOLD` setting (default 3).
7. `feature_prompts/phase1_web_search_instruction.py`: phase-1 instruction builder.
8. `specific_metric_resolution.py`: `_CircuitBreaker` + `_counted_llm_call`; wire discovery to the breaker.
9. `specific_metric_resolution.py`: shaping, budget admission, rejected-turn attribution helpers.
10. `specific_metric_resolution.py`: `_run_phase1_turn`, `_phase1_loop`, `_run_amenity_pipeline`, `_run_amenity_pipelines`, `_sweep_pipeline_results`; extend `run_specific_metric_resolution` (STEP 4 + 5).
11. Tests: new `test_r3_m1_4_phase1_loop.py`; extend C3.1.1, C3.1.2, R3.M1.1, R3.M1.3 tests for the changed contracts.
12. Extend the live sample runner (stage-by-stage STEP 4 + `--entry` full run).
13. Run the full `feature_tests` suite and the live sample runner; report results.

---

## 1. File and Module Structure

| File | New / Modified | Owns |
| --- | --- | --- |
| `backend/src/clients/mcp_tools.py` | Modified | per-kind retry limit inside `_call_with_retry` |
| `backend/src/exceptions/llm.py` | Modified | `LLMFailureClass` + `failure_class` on `LLMProviderError` |
| `backend/src/clients/llm_provider.py` | Modified | tags raise sites; aggregates `cause` on chain exhaustion |
| `backend/src/exceptions/deep_search.py` | Modified | `ProviderFailureCause`; required `cause` on `MetricResolutionProviderError` |
| `backend/src/core/config.py` | Modified | breaker threshold setting |
| `backend/src/services/deep_search/phase_tool_catalog.py` | Modified | R3.M1.1 steps 3-5 (reusable by phase 2) |
| `backend/src/services/deep_search/feature_schemas/schemas.py` | Modified | phase-1 contracts, evidence store, temporary state field |
| `backend/src/services/deep_search/feature_prompts/phase1_web_search_instruction.py` | **New** | phase-1 instruction text and builder |
| `backend/src/services/deep_search/specific_metric_resolution.py` | Modified | breaker, STEP 4/5, phase-1 stage methods, shaping helpers |
| `backend/src/services/deep_search/deep_search.py` | Modified | passes breaker threshold through the composition root |
| `backend/src/services/deep_search/feature_tests/test_r3_m1_4_phase1_loop.py` | **New** | phase-1, breaker, STEP 4/5 behavior suite |
| `feature_tests/test_c3_1_1_mcp_tool_gateway.py`, `test_c3_1_2_structured_llm_caller.py`, `test_r3_m1_1_phase_tool_catalog.py`, `test_r3_m1_3_*.py` | Modified | updated waits; cause tests; steps 3-5 tests; breaker param |
| `backend/src/services/deep_search/feature_sample_runs/r3_m1_3_website_url_discovery_sample_run.py` | Modified (**live sample runner**) | full `run_specific_metric_resolution` walk incl. STEP 4 phase 1 |

Only one new production file (the prompt module, matching the one-prompt-module-per-mechanism convention). Shaping, budget and breaker live in the service module because only it uses them today.

---

## 2. Contracts, Blueprint and Runtime Journey

### A. Feature Map

```
Feature: DeepSearch
└─ Responsibility class: SpecificMetricResolution — resolve LLM-defined metrics per amenity
   └─ Entry: run_specific_metric_resolution — open → STEP 1-5 → close
      ├─ STEP 1-2 (built) _build_plan_index, _derive_work_items
      ├─ STEP 3 (built, now breaker-aware) _run_discovery_batch → website_search_results
      ├─ STEP 4 (new) _run_amenity_pipelines — bounded gather of per-amenity pipelines
      │  └─ _run_amenity_pipeline — pipeline catch; runs phase 1 only for now
      │     └─ Mechanism R3.M1.4 step 1: _phase1_loop — turn 1, optional retry turn, coverage
      │        └─ _run_phase1_turn — the shared tool-turn atom (catalog→turn→guard→execute→shape)
      │           ├─ (R3.M1.1 step 2, built) guard_proposed_calls
      │           ├─ (R3.M1.1 steps 3-5, new) build_rejection_outcomes · sanitize_replay_message · prepare_admitted_calls
      │           ├─ (budget) _admit_calls · _attribute_rejected_turn
      │           ├─ (C3.1.1) _execute_web_searches → gateway.search_web
      │           └─ (R3.M1.2) _shape_web_search
      ├─ STEP 5 (new) _sweep_pipeline_results — exception sweep + run-level raise
      └─ Run-scoped actor: _CircuitBreaker (+ _counted_llm_call) — shared by STEP 3 and STEP 4
   Contracts (§B, not runtime methods): Phase1Result · MetricsSourceContent · MetricSearchOutcome · AmenityPhase1Record
   Prompt (§C): build_phase1_search_instruction
   Harness (test-only, not in §E): test_r3_m1_4_phase1_loop.py · live sample runner
```

### B. Data Contracts

| Contract | Purpose | Fields | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `LLMFailureClass` (llm.py) | why one provider failed | `"availability" \| "content"` | literal | provider raise sites → caller |
| `ProviderFailureCause` (deep_search.py) | why the chain failed | `"availability" \| "content" \| "circuit_open"` | literal | caller / breaker → pipeline catch |
| `MetricResolutionProviderError` | typed chain failure | `stage: str` · `cause: ProviderFailureCause` (required) | immutable | `call_turn`, breaker → pipeline catch |
| `RejectedCallOutcome` (catalog) | per-call result of a rejected message | `tool_call_id` · `tool_name` · `category` (`in_catalog`/`out_of_catalog`/`invalid_call_structure`/`withheld`) · `reason_codes: tuple` · `raw_arguments: str` | frozen | Step 3 → Step 4, attribution |
| `PreparedCall` (catalog) | admitted call ready for MCP | `tool_call_id` · `tool_name` · `arguments: dict` (labels stripped) · `metric_labels: tuple[str, ...]` | frozen | Step 5 → budget, execute |
| `MetricEvidenceItem` (schemas) | one distinct finding | `evidence_id: str` (UUID) · `source_kind` · `url: str \| None` · `shaped_text: str` · `retrieved_at: str` · `metric_labels: set[str]` | **mutable** labels only | store → triage, R3.M2 |
| `MetricsSourceContent` (schemas) | amenity evidence set | `items: list[MetricEvidenceItem]` · private index keyed `(source_kind, url, shaped_text)` | **mutable** (append/merge) | phase 1 (later phase 2) → triage, R3.M2 |
| `MetricSearchOutcome` (schemas) | per-metric budget ledger row | `label` · `status` (`not_searched`/`ok`/`empty`/`failed`) · `attempts_used: int` · `failure_kind: str \| None` | **mutable** during the loop | `_phase1_loop` → triage, R3.M2 reasons |
| `Phase1Result` (schemas) | phase-1 handoff | `messages: list[dict]` · `metrics_source_content` · `metric_outcomes: dict[str, MetricSearchOutcome]` · `uncovered_labels: tuple` · `turns_run: int` | messages mutable (shared conversation) | `_phase1_loop` → triage (later) |
| `AmenityPhase1Record` (schemas) | one pipeline's result | `category_id` · `place_id` · `outcome` (`completed`/`resolution_call_failed`/`pipeline_error`) · `phase1: Phase1Result \| None` · `failed_stage` · `failed_cause` | frozen | pipeline / sweep → `state.phase1_results` |
| `AmenitySearchState.phase1_results` | **temporary** STEP 4 store | `dict[tuple[int, str], AmenityPhase1Record]` | written once after barrier | STEP 4 → sample runner, triage (later) |
| `_ShapedToolResult` (service, private) | one tool message + its status | `tool_call_id` · `metric_label` · `status` · `message: dict` · `result: WebSearchResult \| None` · `failure_kind` | frozen | `_shape_web_search` → turn, recording |
| `_CircuitBreaker` (service, private) | run-scoped breaker state | `threshold: int` · `counter: int` · `open: bool` | **mutable**, one per run | entry → discovery, pipelines |

Rules: evidence is discarded on provider failure (`phase1 = None`); `metric_labels` never empty for web items; the tool-message JSON is `{status, metric_label, objective, search_queries, hits:[{url, title, text}]}` for ok/empty and `{status: "failed", metric_label, failure}` for failed; `shaped_text` is built from the same `title` and `text` the message carries.

### C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `StructuredLLMCaller` | concrete (built) | `call_turn(messages, tools, tool_choice, stage, provider_error_cls) -> AssistantTurn [raises: provider_error_cls]` | one | `_run_phase1_turn`, discovery |
| `ToolGateway` | Protocol (built) | `search_web(objective, search_queries) -> WebSearchResult \| ToolFailure` | MCP gateway, test fake | `_execute_web_searches` |
| `build_tool_catalog` / `guard_proposed_calls` | functions (built) | catalog for `metric_web_search`; whole-message `GuardDecision` | one | STEP 4, `_run_phase1_turn` |
| R3.M1.1 steps 3-5 | functions (new) | see §D | one | `_run_phase1_turn` |
| `build_phase1_search_instruction` | prompt function (new) | `(rec, taxonomy_node, website_url, metrics) -> str` | one | `_phase1_loop` |

### D. Class & Method Blueprint

**Prerequisites (clients / exceptions)**

| Method | Signature | Purpose |
| --- | --- | --- |
| `_call_with_retry` (mcp_tools) | unchanged signature | retry count read from the failed kind's own backoff tuple |
| `LLMProviderError.__init__` | `(message: str, *, failure_class: LLMFailureClass = "content")` | carry why one provider failed |
| `_chain_cause` (llm_provider) | `(classes: Sequence[LLMFailureClass]) -> LLMFailureClass` | all availability → availability, else content |
| `call_turn` / `call_structured` | unchanged signatures `[raises: provider_error_cls]` | pass `cause` when the class declares `carries_cause` |
| `MetricResolutionProviderError.__init__` | `(message: str, *, stage: str \| None = None, cause: ProviderFailureCause)` | required cause next to stage |

**R3.M1.1 steps 3-5 (phase_tool_catalog.py, module functions)**

| Method | Signature | Purpose |
| --- | --- | --- |
| `build_rejection_outcomes` | `(proposed_calls: Sequence[ToolCall], decision: GuardDecision) -> tuple[RejectedCallOutcome, ...]` | one outcome per id'd call, withheld siblings included |
| `sanitize_replay_message` | `(assistant_message: dict, outcomes: Sequence[RejectedCallOutcome]) -> dict \| None` | drop out-of-catalog calls; None if nothing remains |
| `prepare_admitted_calls` | `(validated_calls: Sequence[ValidatedCall], context: ToolContext) -> tuple[PreparedCall, ...]` | strip injected LLM fields into `metric_labels` |

**`MetricsSourceContent` (schemas.py)**

| Method | Signature | Purpose |
| --- | --- | --- |
| `record` | `(source_kind, url, shaped_text, retrieved_at, metric_label) -> MetricEvidenceItem [mutates: self.items]` | add item or merge label by identity triple |
| `items_for` | `(metric_label: str) -> tuple[MetricEvidenceItem, ...]` | one metric's evidence bucket |

**`_CircuitBreaker` (service, private dataclass)**

| Method | Signature | Purpose |
| --- | --- | --- |
| `check` | `(stage: str) -> None [raises: MetricResolutionProviderError(cause=circuit_open)]` | stop the call when open |
| `record_success` | `() -> None [mutates: counter]` | reset counter to 0 |
| `record_failure` | `(cause: ProviderFailureCause) -> None [mutates: counter, open]` | +1 on availability; trip at threshold |

**`SpecificMetricResolution` (new / changed methods)**

| Method | Signature | Purpose |
| --- | --- | --- |
| `__init__` | `(..., breaker_threshold: int = BREAKER_THRESHOLD_DEFAULT)` | store threshold for per-run breakers |
| `run_specific_metric_resolution` | `(state) -> AmenitySearchState [raises: MetricResolutionProviderError, MetricResolutionValidationError, McpGatewayError] [mutates: state.phase1_results]` | adds breaker, STEP 4, STEP 5 |
| `_counted_llm_call` | `(breaker: _CircuitBreaker, awaitable: Awaitable[T]) -> T [raises: MetricResolutionProviderError]` | await an LLM call; feed outcome to breaker |
| `_run_discovery_batch` / `_discover_website_url` | gain `breaker: _CircuitBreaker` | open breaker → `none` before Stage 1 |
| `_run_discovery_search` / `_select_candidate` | gain `breaker` | LLM calls go through `_counted_llm_call` |
| `_run_amenity_pipelines` | `(state, work_items, catalog, breaker) -> list[AmenityPhase1Record \| BaseException]` | bounded gather; hard barrier |
| `_run_amenity_pipeline` | `(work_item, rec, website, catalog, breaker, run_id) -> AmenityPhase1Record` | pipeline catch around phase 1 |
| `_phase1_loop` | `(work_item, rec, website, catalog, breaker, run_id) -> Phase1Result [raises: MetricResolutionProviderError]` | turn 1, optional retry, coverage |
| `_run_phase1_turn` | `(messages, catalog, ledger, turn, store, breaker, key, run_id) -> tuple[_ShapedToolResult, ...] [mutates: messages, ledger, store] [raises: MetricResolutionProviderError]` | one atom pass on the shared history |
| `_execute_web_searches` | `(calls: Sequence[PreparedCall]) -> list[WebSearchResult \| ToolFailure]` | gather admitted searches; map raises to failures |
| `_sweep_pipeline_results` | `(work_items, results, breaker, run_id) -> dict[key, AmenityPhase1Record] [raises: MetricResolutionProviderError]` | exception sweep; run-level raise |

**Module helpers (service)**

| Function | Signature | Purpose |
| --- | --- | --- |
| `_new_ledger` | `(metrics: Sequence[MetricSpec]) -> dict[str, MetricSearchOutcome]` | one `not_searched` row per metric |
| `_admit_calls` | `(calls, ledger, turn) -> tuple[list[PreparedCall], list[tuple[PreparedCall, str]]] [mutates: ledger]` | split executable vs not-executed with reason |
| `_attribute_rejected_turn` | `(outcomes, ledger, turn) -> tuple[str, ...] [mutates: ledger]` | spend an attempt for each label found in a rejected turn |
| `_shape_web_search` | `(tool_call_id, metric_label, outcome) -> _ShapedToolResult` | ordered guard: failed, then ok/empty |
| `_shape_not_executed` | `(tool_call_id, metric_label, reason) -> _ShapedToolResult` | failed tool message for a call never sent |
| `_failure_phrase` | `(kind: str) -> str` | `timeout` → "timed out", etc. |
| `_record_web_evidence` | `(shaped, store) -> int [mutates: store]` | one item per hit of each ok result |
| `_retry_eligible` | `(ledger) -> tuple[str, ...]` | labels with status failed and attempts_used 1 |

### E. Runtime Flow: Data Object Journey

| # | Stage | Reads | Produces / mutates | Shape after |
| --- | --- | --- | --- | --- |
| 1 | entry: open, STEP 1-2 | state | `plan_index`, `work_items` | unchanged state |
| 2 | entry: build breaker + catalog | settings, raw defs | `_CircuitBreaker(counter=0)`, `metric_web_search` catalog | catalog raises → run fails before any LLM call |
| 3 | STEP 3 discovery (breaker-aware) | work items, breaker | `website_search_results` (all N) | RC8 holds |
| 4 | STEP 4 `_run_amenity_pipelines` | work items, verdicts | N tasks under `AMENITY_PIPELINE_CONCURRENCY` | gather barrier |
| 5 | `_phase1_loop` setup | rec, metrics, website | `messages=[system, user]`, `ledger`, empty store | all metrics `not_searched` |
| 6 | turn 1 `_run_phase1_turn` | messages, catalog | assistant msg + one tool msg per kept call; ledger rows; evidence items | ok/empty/failed per tagged metric |
| 7 | retry decision | ledger | none, or retry turn on same messages | eligible = failed with 1 attempt |
| 8 | retry turn (optional) | full history | more tool msgs; final ledger; more evidence | every retried metric final |
| 9 | coverage | ledger | `uncovered_labels` | `Phase1Result` complete |
| 10 | pipeline catch | Phase1Result or error | `AmenityPhase1Record` | provider error → `phase1=None` |
| 11 | STEP 5 sweep | gather results | records for all N; maybe run-level raise | exceptions → `pipeline_error` |
| 12 | entry | records | `state.phase1_results` written | then gateway closes |

```
AmenitySearchState{website_search_results[N]}
 → per work item: messages[system,user] + ledger{label: not_searched,0} + MetricsSourceContent{}
 → turn 1: messages += assistant(tool_calls, minus out_of_catalog) + tool{id, json} × calls
           ledger{label: ok|empty|failed, 1} · store.items += web hits of ok results
 → (retry-eligible ≠ ∅) turn 2: messages += assistant + tool × re-emitted calls · ledger{label: …, 2}
 → Phase1Result{messages, store, metric_outcomes, uncovered_labels, turns_run}
 → AmenityPhase1Record{outcome=completed, phase1}            # success
   | AmenityPhase1Record{outcome=resolution_call_failed, phase1=None, failed_stage, failed_cause}
   | AmenityPhase1Record{outcome=pipeline_error, phase1=None}   # unexpected raise, from sweep
 → state.phase1_results[(cat, place)]
```

**Approach pointers at the decision points**

- *Turn atom order.* Breaker check, then `call_turn(tool_choice="required")` through `_counted_llm_call`. A provider error propagates with nothing appended. Then guard with `validation_context={"metric_labels": set(labels)}`.
- *Accepted turn.* Step 5 prepares calls. `_admit_calls` checks budget per call in assistant-message order. Admitted calls run together; the rest get a not-executed `failed` message. Ledger rows update from shaped status.
- *Rejected turn.* Step 3 builds outcomes. `_attribute_rejected_turn` spends one attempt for each in-set label parsed from the raw arguments (status `failed`, kind `rejected`). Step 4 removes out-of-catalog calls from the assistant message. Every kept call gets a `failed` message naming the reason codes.
- *Budget admission.* Not executed when the metric is `ok`/`empty`, already used 2 attempts, is not retry-eligible on the retry turn, or a sibling call for the same label was already admitted this turn.
- *Append order.* Assistant message first (sanitized), then tool messages in assistant-message order, then evidence recording from ok results.
- *Retry decision.* After turn 1, compute `_retry_eligible`. Empty → no further LLM call. Otherwise one retry turn with no new user message.
- *Coverage.* Labels still `not_searched` after the loop go to `uncovered_labels` (triage later forces them unresolved).
- *Breaker.* `_counted_llm_call` resets on success; on error adds 1 only for `availability`; opens at threshold and logs once. Discovery checks `is open` once before Stage 1. Pipelines check before every `call_turn`.
- *Run-level raise.* After the sweep, if N > 0, no record is `completed`, and at least one is `resolution_call_failed`, write the store and raise with `cause = circuit_open` if the breaker is open, else `availability` when all recorded causes are availability, else `content`.

### F. Method Detail

**`_call_with_retry` (mcp_tools)**
- Counts retries per failure kind. A kind's retries stop at the length of its own tuple: timeout/transport `(2.0,)`, rate limit `(30.0, 30.0)`. The wait index is that kind's own retry count. `Retry-After` handling is unchanged (not implemented today; outside this step).

**`call_turn` / `call_structured`**
- Collect each failed provider's `failure_class`. When the chain is exhausted, raise `provider_error_cls(message, stage=..., cause=_chain_cause(...))` only if the class sets `carries_cause = True`. Otherwise raise as today (R1 classes unchanged). Attempt and rejected log events gain `failure_class` / `cause`.

**`build_phase1_search_instruction`**
- Sections: task statement, rules, the tool-message format, the retry rule, amenity identity (name, taxonomy node, address verbatim, `website_url` or "none"), metrics JSON (`label`, `question`, `value_type`, `unit`, `enum_values`, `evidence_class`, `verification`, `web_target`, app-computed `host_scoping`).
- `host_scoping` is "include at least one query scoped to `site:<host>` alongside off-site queries" for a factual metric when a URL exists, and "do not scope any query to the official site" otherwise.
- One worked example on a public library (not the runner's seed).

**`_run_amenity_pipeline`**
- Catches `MetricResolutionProviderError`, returning `resolution_call_failed` with `stage`/`cause` and discarding evidence. Any other exception propagates to the gather and becomes `pipeline_error` in the sweep. The breaker count happens in `_counted_llm_call`, not here, so it is counted once per failing call, which equals once per amenity because the error ends the amenity.

---

## 3. Async Structure

| Layer / group | Operations and I/O | Dependency | Placement | Ordering | Shared state | Blocking check |
| --- | --- | --- | --- | --- | --- | --- |
| Entry | open → STEP 3 → STEP 4 → STEP 5 → close | data-dependent (URL first, RC8) | event loop | sequential await | state written between barriers | none |
| STEP 4 pipelines | N `_run_amenity_pipeline` coroutines | independent | event loop | `gather(return_exceptions=True)` under a semaphore | partial results returned, merged after barrier; breaker is the one shared object | none |
| Breaker | counter reads/writes | shared across pipelines | event loop | updates happen between awaits | one object, no lock (single event loop, no await inside an update) | none |
| `_phase1_loop` | turn 1 → decision → retry turn | data-dependent (retry reads turn-1 results and history) | event loop | sequential await | messages/ledger/store are per amenity, unshared | none |
| `_run_phase1_turn` | `call_turn` (LLM HTTP) → guard → searches → shape | call_turn before searches; searches independent of each other | event loop | `await call_turn`, then `gather` searches | results returned by value, appended after gather in fixed order | guard (jsonschema) and JSON encoding are short CPU work, run inline |
| Gateway | `search_web` over MCP Streamable HTTP | independent per call | event loop (async-native client) | concurrent, capped by gateway semaphore (4) | gateway semaphore | no offload: async client exists |

No work is moved to a thread or process (offloaded to a worker): every I/O call has an async-native client, and the CPU work is short.

---

## 4. Drift Entries (per method)

**`_call_with_retry`**
- Core: retry transient failures with backoffs chosen per kind.
- Drifts handled: a call that times out then gets a 429 must not mix limits → caught in **core** with per-kind counters → **recover** (each kind keeps its own cap).
- Left out: Retry-After parsing (no observed header in logs; *not live* for this step). Cancel safety (semaphore released by `async with`; *trust*).

**Provider raise sites + `_chain_cause`**
- Core: tag each failure and reduce the chain to one cause.
- Drifts handled: a raise site added later without a class → default `content` → **de-mask** (never silently trips the breaker). Mixed chain → **content** by rule.
- Left out: empty provider list (`create_llm_providers` rejects it; *imaginary*). Non-SDK exceptions escaping a provider (propagate as today; *wrong boundary*).

**`build_rejection_outcomes` / `sanitize_replay_message`**
- Core: one outcome per id'd call; replay keeps in-catalog calls, drops out-of-catalog ones.
- Drifts handled: every call out-of-catalog leaves an assistant message with no calls → **core** returns None → caller does not append it (no dangling turn).
- Left out: duplicate or missing call ids (provider SDKs generate unique ids; *trust*; a violation is loud at the next API call). Empty call list (`tool_choice="required"`; *imaginary*).

**`prepare_admitted_calls`**
- Core: strip injected LLM fields per context policy into `metric_labels`.
- Drifts handled: none live (input already guard-validated).
- Left out: label type re-check (guard enforces schema; *trust*). App-injected args for web_search (none exist; *not live*).

**`MetricsSourceContent.record`**
- Core: add or merge by `(source_kind, url, shaped_text)`.
- Drifts handled: same hit returned twice in one call → **core** identity index → **merge** (one item, labels unioned).
- Left out: concurrent writers (per-amenity store, written after gather; *not live*). Very long text (stored as the LLM saw it; *trust*).

**`_CircuitBreaker` + `_counted_llm_call`**
- Core: count consecutive availability failures; stop calls once open.
- Drifts handled: outage → threshold reached → **core** opens and WARN-logs once → later calls **reject** with `circuit_open`. A `circuit_open` or `content` error must not move the counter → **core** rule.
- Left out: lock around the counter (single event loop, no await inside updates; *not live*). Half-open recovery (spec: open for rest of run; *business rule given*).

**`_discover_website_url` (changed)**
- Core: unchanged Stage 1, now skipped when the breaker is open.
- Drifts handled: breaker open → **core** → **degrade** to `none`, WARN `discovery_degraded(reason=circuit_open)`.
- Left out: checking before the selection turn too (spec check point is Stage-1 start only; *business rule given*).

**`_run_amenity_pipelines`**
- Core: run all pipelines concurrently under a cap and wait for all.
- Drifts handled: an unexpected raise in one pipeline → **core** `return_exceptions=True` → **propagate as value** to the sweep (siblings keep running). Missing verdict for a key → **core** treats as `WebsiteSearchResult(None, "none")` with WARN (RC8 says it cannot happen; de-mask instead of KeyError).
- Left out: per-pipeline timeout (each LLM and tool call is already bounded by client timeouts; *wrong boundary*).

**`_run_amenity_pipeline`**
- Core: run phase 1, return a record.
- Drifts handled: provider error (any cause) → **core** catch → **degrade** to `resolution_call_failed`, WARN with stage + cause, evidence discarded. Missing `PredefinedMetricsRecord` → **core** → **degrade** to `pipeline_error` record, WARN (no identity to search with).
- Left out: catching all exceptions here (sweep owns unexpected raises; *wrong boundary*).

**`_phase1_loop`**
- Core: turn 1, optional retry turn, coverage.
- Drifts handled: LLM tags no call for a metric → **core** coverage → **degrade** (`uncovered_labels`, WARN). Metric still `failed` after its retry → **core** → **degrade**, kept as `failed` for triage (incomplete evidence).
- Left out: a reply with no tool calls (`tool_choice="required"` rules it out; *imaginary*). A third turn (budget forbids; *business rule given*).

**`_run_phase1_turn`**
- Core: one atom pass with full history bookkeeping.
- Drifts handled: guard rejects the whole message → **core** → **recover** (attempt spent, failed tool messages, retry turn may follow). LLM re-emits a done metric or duplicates a label → **core** budget admission → **reject that call** (not executed, failed message, WARN). Out-of-catalog call → **core** Step 4 strip.
- Left out: re-validating arguments after the guard (*trust*). Provider error handling (propagates; *wrong boundary*).

**`_execute_web_searches`**
- Core: run admitted searches together.
- Drifts handled: `search_web` raises `ValueError` on a blank objective/query (guard does not check blanks, by spec) → **core** `_search_once` → **degrade** to `ToolFailure(tool_error)`. Any other raise → **core** `gather(return_exceptions=True)` → **degrade** to `ToolFailure(tool_error)`, WARN.
- Left out: gateway retries (owned by gateway; *wrong boundary*). Timeouts (gateway per-call timeout; *wrong boundary*).

**`_shape_web_search`**
- Core: `ToolFailure` → failed; zero excerpts → empty; else ok.
- Drifts handled: none beyond the ordered guard (termination checked before content, so a failure is never shaped `empty`).
- Left out: partial payload on failure (failure carries no payload; *not live*).

**`_sweep_pipeline_results`**
- Core: convert gather results to records; decide run-level raise.
- Drifts handled: exception slot → **core** → **degrade** to `pipeline_error`, ERROR log (a bug). Every pipeline provider-failed → **core** → **reject** run with `MetricResolutionProviderError` after writing the store.
- Left out: N = 0 (no raise by rule; covered by the condition). Cancellation of the run (propagates; *wrong boundary*).

**`build_phase1_search_instruction`**
- Core: render the instruction.
- Drifts handled: `website_url` None → "none" and no host scoping for any metric. Name/address missing → "(unavailable)" placeholders (same as discovery).
- Left out: unparseable `website_url` host (URLs come from the gate or candidate set; *trust*).

---

## 5. Log Plan

All lines are structured JSON on the deep-search logger, threaded by `run_id` (STEP 4) or `batch_id` (STEP 3) plus `category_id` / `place_id`. No keys, no evidence text at INFO/WARN.

| Event | Level | Node type | Driving state |
| --- | --- | --- | --- |
| `llm_provider.attempt` (changed) | INFO | boundary | adds `failure_class` on failed attempts |
| `llm_provider.rejected` (changed) | INFO | boundary | adds `cause` |
| `r3m1_5.breaker_opened` | WARN | state change + drift | `threshold`, `counter`, `stage` of the tripping call |
| `r3m1_3.discovery_degraded` (reason `circuit_open`) | WARN | drift | existing fields |
| `r3m1_4.pipelines_start` | INFO | boundary | `run_id`, `work_items`, `concurrency` |
| `r3m1_4.phase1_turn` | INFO | boundary | `turn`, `provider`, `guard_decision`, `proposed`, `executed`, `not_executed`, status counts |
| `r3m1_4.guard_rejected` | WARN | drift | `turn`, `reason_codes`, `attributed_labels`, `stripped_out_of_catalog` |
| `r3m1_4.call_not_executed` | WARN | drift | `turn`, `metric_label`, `reason` |
| `r3m1_4.search_failed` | WARN | drift | `turn`, `metric_label`, `failure_kind` |
| `r3m1_4.metrics_uncovered` | WARN | drift | `labels` |
| `r3m1_4.phase1_done` | INFO | state change | `turns_run`, per-status counts, `evidence_items`, `retried_labels` |
| `r3m1_4.pipeline_provider_failed` | WARN | drift | `stage`, `cause` |
| `r3m1_4.pipeline_crashed` | ERROR | failure | `error_type`, `message` |
| `r3m1_4.pipelines_done` | INFO | boundary | `completed`, `resolution_call_failed`, `pipeline_error`, `breaker_open` |
| `r3m1_4.object_finalized` | DEBUG | state change | `Phase1Result` summary, evidence ids/urls per label |

Not logged: entering methods, successful searches individually (counted in `phase1_turn`), deterministic helper outputs.

---

## 6. Sample Runner and Fixture Set

### 6.1 Live sample runner (required, extended file)

- **File:** `feature_sample_runs/r3_m1_3_website_url_discovery_sample_run.py` (extended; docstring retitled to cover R3.M1.3 + R3.M1.4 phase 1).
- **Run (from `backend/`):**
  - stage-by-stage: `python -m src.services.deep_search.feature_sample_runs.r3_m1_3_website_url_discovery_sample_run`
  - full entry: same command with `--entry` (one `run_specific_metric_resolution` call).
- **Seed** (dummy M1.3 handoff, no earlier mechanism called): category 1 `museum`, two records. Rijksmuseum with its Google site (gate-official, no search). Museum Van Loon with an empty website (declined, live discovery). Three real `MetricSpec`s: factual boolean `museumkaart_free_entry`, factual number `adult_ticket_price` (EUR), experiential enum `weekday_afternoon_crowding` (`quiet`/`moderate`/`busy`). None reuse the prompt's library worked example.
- **Prints, one titled section each:** seed state, STEP 0 open + tool defs, STEP 1, STEP 2, STEP 3 stage 0 and stage 1 (as today, now with breaker), STEP 4 catalog for `metric_web_search`, phase-1 instruction for each amenity, turn 1 (provider attempts, guard decision, each tool message status, evidence items), retry decision and retry turn when it runs, `Phase1Result` summary (ledger, uncovered, evidence per label), STEP 5 records, breaker state, RESULT checkpoints.
- **Checkpoints:** RC8 holds; every work item has an `AmenityPhase1Record`; every tool call id in each conversation has exactly one tool message; no metric has more than 2 attempts. Typed failure prints exception class, `stage`, `cause`, message and exits non-zero. Nothing written to disk.

### 6.2 Fixture set (pytest, no live calls)

New `test_r3_m1_4_phase1_loop.py`, using the existing fake provider/gateway pattern (gateway outcomes keyed by objective so `gather` order does not matter):
1. All metrics ok on turn 1 → one LLM call, no retry turn, evidence items per hit, labels set.
2. One metric `failed` → retry turn re-emits only it; final status from the retry.
3. `empty` is terminal: never retried, attempts_used 1.
4. Guard rejection of turn 1 → every attributed metric spends an attempt, retry turn runs, out-of-catalog call stripped from history.
5. Retry turn re-emits a done metric and a duplicate → not executed, failed tool message, ledger unchanged.
6. Untagged metric → `uncovered_labels`.
7. Provider error on turn 1 and on the retry turn → `resolution_call_failed`, `phase1=None`, nothing appended.
8. Breaker: 3 availability failures open it; later pipelines get `circuit_open` with no search; discovery returns `none`; a success resets the counter; `content` never counts.
9. STEP 5: an exception slot → `pipeline_error`; all provider-failed → run raises with the right `cause`; mix with one completed → no raise.
10. Evidence identity: same triple merges; same URL with different text stays two items.
11. Every tool_call_id answered exactly once across both turns.
12. Host scoping in the rendered instruction: factual with URL, factual without URL, experiential.

Extended suites: C3.1.1 waits `[2.0]` and `[30.0, 30.0]` plus a mixed-kind case; C3.1.2 cause aggregation (all timeouts → availability; refusal + timeout → content; R1 class raised unchanged); R3.M1.1 steps 3-5; R3.M1.3 call sites pass a breaker.

---

## 7. Verification

1. From `backend/`: `python -m pytest src/services/deep_search/feature_tests -q` (asyncio auto mode). All existing and new tests pass.
2. Live runner, stage-by-stage, then `--entry`; needs `PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, `OPENAI_API_KEY`/`GROQ_API_KEY`. Expect about 7 billed searches (1 discovery + 6 phase-1) plus any retries.
3. Check the runner output: one tool message per call id, the factual metrics on the Rijksmuseum show a `site:rijksmuseum.nl` query next to off-site queries, the crowding metric shows none.

---

## 8. Architecture & Modularity Decisions

### Layer 1: Glance

**A. Shape.** One responsibility class (`SpecificMetricResolution`) gains stage methods for STEP 4/5 and phase 1, built on two existing infrastructure seams (LLM caller, MCP gateway) and pure module functions for guard steps, shaping and budget.

- **Seams:**
  - LLM provider chain: OpenAI vs Groq order, chosen by `LLM_PROVIDER_ORDER`.
  - Tool gateway: real MCP gateway vs test fake (existing `ToolGateway` Protocol).
  - Error-class contract: a service error class opts into `cause` via `carries_cause`, so the client layer never imports service exceptions.
- **Components:**
  - `SpecificMetricResolution`: orchestrates STEP 3-5 and phase 1.
  - `_CircuitBreaker`: run-scoped availability counter shared by discovery and pipelines.
  - R3.M1.1 steps 3-5: rejected-turn outcomes, replay cleanup, admitted-call preparation.
  - R3.M1.2 shaping helpers: every call → one ok/empty/failed tool message.
  - `MetricsSourceContent`: normalized evidence set with identity merge.
  - Phase-1 prompt module: instruction text and rendering.

### Layer 2: Justification

**B. Component Map**

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `SpecificMetricResolution` | STEP 3-5, phase-1 loop, pipeline catch | caller, gateway, catalog fns, prompt | — (concrete) |
| `ToolGateway` | MCP calls | — | Yes: existing Protocol, test fake needed |
| `StructuredLLMCaller` | provider chain, cause aggregation | providers | — (concrete, built) |
| `_CircuitBreaker` | counter, trip, check | `MetricResolutionProviderError` | — (concrete) |
| Steps 3-5 functions | rejection outcomes, replay, preparation | `GuardDecision`, policy table | — (functions) |
| Shaping / budget helpers | tool messages, admission | gateway result types | — (functions) |
| `MetricsSourceContent` | evidence items + identity index | — | — (concrete) |
| `build_phase1_search_instruction` | prompt text | `MetricSpec` | — (function) |

**C. Decisions & Justifications**

| Decision | Requirement that forced it | What breaks today without it |
| --- | --- | --- |
| `carries_cause` opt-in on error classes | `cause` required on M3 errors; R1 errors unchanged | caller must import service errors or R1 classes break |
| `failure_class` on `LLMProviderError` | breaker counts only availability | no failure can be labelled availability; breaker never trips |
| Run-scoped `_CircuitBreaker` object | one counter shared by discovery and N pipelines | counts split per caller; trip rule unenforceable |
| `_counted_llm_call` single funnel | every LLM success resets, every availability failure counts | resets/counts scattered across 4 call sites, easy to miss one |
| Steps 3-5 as module functions in catalog module | spec places them in R3.M1.1; phase 2 reuses them | rejected turns leave unanswered tool calls in the shared history |
| `MetricsSourceContent` with identity index | identity-triple merge rule; per-metric buckets | duplicate items or collapsed same-URL excerpts |
| Temporary `state.phase1_results` | phase-1 output must be visible before triage exists | runner and later steps cannot read phase-1 output |
| New prompt module | prompt-per-mechanism convention; text owned apart from logic | instruction text mixed into stage code |

**D. Kept Concrete / Rejected**

| Considered | Decision | Reason |
| --- | --- | --- |
| Breaker Protocol / interface | kept concrete | one implementation, tests use the real one |
| Separate LLM-call semaphore | not added | pipeline cap already bounds in-flight LLM calls to one per pipeline |
| Generic `ToolTurnRunner` class | not added | one consumer today (phase 1); a method suffices |
| Separate module for shaping/budget | not added | used only by the service module today |
| Ledger class | not added | `dict[label, MetricSearchOutcome]` plus pure functions covers it |
| New sample-runner file | not added | you asked to extend the existing runner |
| Per-pipeline timeout | not added | every call already has a client timeout |

### Layer 3: Wiring

**E. Dependency Direction**

```
SpecificMetricResolution → [ToolGateway] ← McpToolGateway, FakeGateway
SpecificMetricResolution → StructuredLLMCaller → [StructuredLLMProvider] ← OpenAI, Groq
SpecificMetricResolution → phase_tool_catalog fns, phase1 prompt, schemas contracts
StructuredLLMCaller → provider_error_cls (reads carries_cause; never imports services)
```

**F. Composition Root**
- **Where:** `create_specific_metric_resolution(settings, llm_caller=...)` called from `deep_search.py`.
- **Selects:** MCP gateway from settings, shared caller from the feature, `breaker_threshold` from `METRIC_RESOLUTION_BREAKER_THRESHOLD` (default 3).

**G. End-to-End Flow**
1. `DeepSearch` calls `run_specific_metric_resolution(state)`.
2. Gateway opens; plan index and work items are built.
3. A breaker is created; discovery fills `website_search_results` (skips Stage 1 when open).
4. The `metric_web_search` catalog is built once.
5. Pipelines run concurrently; each runs `_phase1_loop` through `_run_phase1_turn` up to twice.
6. The sweep converts results to `AmenityPhase1Record`s and applies the run-level raise.
7. `state.phase1_results` is written; the gateway closes.

### Layer 4: Backing (reasoning for Layer 3)

- **Opt-in `carries_cause`.** The caller already receives the error class by injection; a class attribute keeps the client layer free of service imports while making `cause` mandatory where M3 needs it.
- **Breaker passed as a parameter, not stored on `self`.** A service instance can serve more than one run; per-run state on `self` would leak between runs.
- **Count in `_counted_llm_call`, not the pipeline catch.** Discovery needs per-call counting; a provider error ends a pipeline, so per-call and per-amenity counts are equal for pipelines.
- **Catalog built once per run.** Raw definitions are fixed after `open()`; a build failure is a gateway/schema mismatch and fails the run before any LLM spend.
- **Records written after the barrier.** Pipelines return values, so no concurrent writes to `state` happen during the gather (partial-results-and-merge).
