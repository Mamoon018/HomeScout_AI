# R3.M1.1 — Implementation Plan: Build the Phase-Scoped Tool Catalog and Call Guard

> Implementation plan for sub-component **R3.M1.1** of Responsibility 3 (Specific Metric
> Resolution). Grounded in `R3_Specific_Metric_Resolution_spec.md` (lines 166–409),
> `R3_M1_1_Dry_Run_Traceflow.md`, and the already-built C3.1.1 gateway
> (`clients/mcp_tools.py`) and C3.1.2 caller (`clients/llm_provider.py`). Skills applied:
> Implementation_architecture_skill, Plan_output_format, architecture-decisions-plan-format,
> async_app_skill, drift_analyzer, logs_recorder.
>
> **Status: PLAN — not yet built.** No application code, canonical markdown, or sample runner
> is written until this plan is accepted. The Build checklist at the end is executed in order
> only after confirmation.

---

## Scope recap

Two **reusable, LLM-agnostic** abstractions, used in sequence by any workflow caller preparing
a tool turn:

1. **Build LLM-Facing Tool Catalog** — `build_tool_catalog(raw_tool_definitions, context)`.
   Pure schema derivation: pick server+tool by context policy, derive a controlled copy of the
   MCP input schema (allowlist server fields, inject app-defined LLM-facing fields, preserve
   `$ref`/`$defs`), adapt to the Chat-Completions function-tool shape. No LLM, no execution, no
   state mutation.
2. **Guard Proposed Calls** —
   `guard_proposed_calls(proposed_tool_calls, tool_catalog, context, validation_context)`.
   Whole-message validation: structure → catalog membership → arg-JSON decode → schema →
   optional data-dependent validator; all-or-nothing accept/reject. No execution, no history
   mutation, no retry decision.

Both are pure functions (no `self`), consistent with the dry-run traceflow calling them as free
functions and with the spec's "any workflow caller can use it."

---

## Section 1 — File and Module Structure

| File | Status | Owns |
|---|---|---|
| `backend/src/services/deep_search/phase_tool_catalog.py` | **NEW** | Both abstractions as module-level functions; the `ToolContext` literal; the context→policy table; schema-restriction + `$ref`/`$defs` helpers; the `AdditionalValidator` Protocol; the metric-label validator; result/error dataclasses (`GuardDecision`, `ValidatedCall`, `GuardError`, `ValidationIssue`). |
| `backend/src/exceptions/deep_search.py` | **EDIT** | Add `MetricResolutionValidationError(MetricResolutionError)` — raised by catalog construction only (the guard returns decisions, never raises for validation). |
| `backend/src/services/deep_search/feature_sample_runs/r3_m1_1_tool_catalog_guard_sample_run.py` | **NEW** | Live, stage-by-stage sample runner (Section 4.1), following the `R3_M1_1_Dry_Run_Traceflow.md` plan. |
| `backend/src/services/deep_search/feature_tests/test_r3_m1_1_phase_tool_catalog.py` | **NEW** | Dummy-provider / fixture pytest set (Section 4.2); deterministic code-path assertions, no live calls. |

**No prompt module.** R3.M1.1 calls no LLM. The catalog preserves the server's own field
descriptions; the query word-count/diversity guidance "remain instructions" owned by the
message-constructing caller (R3.M1.3/R3.M1.4), not this sub-component — exactly as the gateway
runner notes "no prompt module, no worked-pair examples."

**No new methods on `SpecificMetricResolution` yet.** The orchestration that calls these
functions is R3.M1.3 (discovery) / R3.M1.4 (phase loop). Adding stage methods now would bind
reusable functions to one responsibility before a caller exists. The functions are the
mechanism's reusable core; later stage methods will call them.

**No `schemas.py` change.** `RawToolDefinition` / `RawToolDefinitions` already exist in
`clients/mcp_tools.py`; `proposed_tool_calls` is already `ToolCall` from
`clients/llm_provider.py`. The guard accepts `Sequence[ToolCall]` and reuses those contracts
rather than defining parallel types. The `state.raw_tool_definitions` field named in the spec is
R3.M1.5 orchestration work, out of this sub-component — the runner passes
`gateway.get_tool_definitions()` directly, as the gateway runner already does.

---

## A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: DeepSearch — owns shared caller; sequences R1→R2→R3
   └─ Responsibility: SpecificMetricResolution (R3) — resolve specific metrics
      └─ Mechanism R3.M1 Workflow: Evidence Acquisition
         └─ Sub-component R3.M1.1: Phase-Scoped Tool Catalog and Call Guard
            ├─ Abstraction 1: build_tool_catalog — MCP schema → controlled function-tool
            │   ├─ select_server_and_tool — context policy picks parallel/firecrawl + tool
            │   ├─ derive_controlled_schema — allowlist + inject fields + preserve $defs
            │   └─ adapt_to_function_tool — wrap as {type:function, function:{…}}
            └─ Abstraction 2: guard_proposed_calls — whole-message validation
                ├─ (ordered) structure → catalog → decode → schema → validator
                └─ metric_label_membership_validator (AdditionalValidator impl)
```

## B. Data Contracts

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
|---|---|---|---|---|
| `RawToolDefinition` *(exists)* | one server tool's full def | `name: str` · `description: str\|None` · `input_schema: dict` | immutable | gateway → `build_tool_catalog` |
| `ToolContext` | context literal | one of `website_discovery` `metric_web_search` `site_map` `metric_scrape` | immutable | caller → both abstractions |
| tool_catalog | LLM-facing function tools | `list[dict]` in `{type:"function", function:{name, description, parameters}}` | immutable | `build_tool_catalog` → `call_turn`, guard |
| `ToolCall` *(exists)* | one proposed call | `id: str` · `name: str` · `arguments: str` (raw JSON) | immutable | caller → guard |
| `ValidationIssue` | one validator finding | `reason_code: str` · `explanation: str` · `field_path: str\|None` | immutable | validator → guard |
| `GuardError` | one guard failure | `reason_code` · `explanation` · `call_index: int\|None` · `tool_call_id: str\|None` · `tool_name: str\|None` · `category: str\|None` · `field_path: str\|None` | immutable | guard → caller |
| `ValidatedCall` | one admitted call | `tool_call_id: str` · `tool_name: str` · `arguments: dict` (decoded) | immutable | guard → caller |
| `GuardDecision` | message-level result | `decision: "accepted"\|"rejected"` · `validated_calls: tuple[ValidatedCall,…]` · `errors: tuple[GuardError,…]` | immutable | guard → caller |

Rules surfaced: empty/`[]` not omitted; `category` is `null` for `no_tool_calls`; accepted ⇒
`errors` empty + all calls in original order; rejected ⇒ `validated_calls` empty.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementations | Depended on by |
|---|---|---|---|---|
| `AdditionalValidator` | Protocol | `validate(arguments: dict, validation_context: Any) -> list[ValidationIssue]` | `metric_label_membership_validator` (concrete) | `guard_proposed_calls` step 6 |
| `Draft202012Validator` | lib (`jsonschema==4.26.0`) | `iter_errors(instance) -> Iterator[ValidationError]` | one | guard step 5 |
| `ToolGateway.get_tool_definitions` *(exists)* | method | `() -> RawToolDefinitions` | `McpToolGateway` | sample runner (source of real defs) |

## D. Class & Method Blueprint (module-level functions)

**`phase_tool_catalog`** — the two abstractions + policy table + helpers.

| Function | Signature | Purpose |
|---|---|---|
| `build_tool_catalog` | `(raw_tool_definitions: RawToolDefinitions, context: ToolContext) -> list[dict] [raises: MetricResolutionValidationError]` | derive one controlled function-tool for the context |
| `_select_definition` | `(raw: RawToolDefinitions, context) -> RawToolDefinition [raises: MetricResolutionValidationError]` | apply policy; fail if server/tool missing |
| `_derive_controlled_schema` | `(input_schema: dict, policy: _Policy) -> dict [raises: MetricResolutionValidationError]` | allowlist kept fields, inject app fields, carry `$defs`, resolve-check |
| `_carry_referenced_defs` | `(kept: dict, source_defs: dict) -> dict [raises: MetricResolutionValidationError]` | collect transitive `$ref` targets; fail if unresolved |
| `_adapt_to_function_tool` | `(name, description, parameters: dict) -> dict` | wrap in Chat-Completions function-tool shape |
| `guard_proposed_calls` | `(proposed_tool_calls: Sequence[ToolCall], tool_catalog: list[dict], context: ToolContext, validation_context: Any\|None) -> GuardDecision` | whole-message validate; accept-all or reject-all |
| `_schema_by_tool_name` | `(tool_catalog) -> dict[str, dict]` | index catalog parameters by tool name |
| `metric_label_membership_validator` | `(arguments: dict, validation_context: Any) -> list[ValidationIssue]` | `metric_label ∈ validation_context["metric_labels"]` else one issue |
| `_validator_for` | `(tool_name: str, context: ToolContext) -> AdditionalValidator\|None` | select validator by tool+context |

**Context policy table** (`_CONTEXT_POLICY: dict[ToolContext, _Policy]`),
`_Policy(server, tool, kept_fields, required, injected_fields, validator)`:

| Context | server / tool | kept server fields | injected LLM fields | validator |
|---|---|---|---|---|
| `website_discovery` | parallel / web_search | `objective`, `search_queries` (`minItems:1`) | — | — |
| `metric_web_search` | parallel / web_search | `objective`, `search_queries` | `metric_label` (required str) | metric-label |
| `site_map` | firecrawl / firecrawl_map | — | — | — |
| `metric_scrape` | firecrawl / firecrawl_scrape | — (url/formats dropped) | `id` (required str), `metric_label` (required str) | metric-label |

All controlled schemas set `additionalProperties:false` and an explicit `required` list.

## E. Runtime Flow — Data Object Journey

| # | Step | Reads | Produces / mutates | Shape after |
|---|---|---|---|---|
| 1 | `build_tool_catalog` | `raw_tool_definitions`, `context` | `tool_catalog: list[dict]` | one function-tool, controlled params |
| 2 | *(caller builds message, calls `call_turn`)* | tool_catalog | `AssistantTurn.tool_calls` | `Sequence[ToolCall]` |
| 3 | `guard_proposed_calls` | tool_calls, tool_catalog, context, validation_context | `GuardDecision` | accepted(validated_calls) **or** rejected(errors) |

**Shape trace:**
```
RawToolDefinitions
 → tool_catalog: list[dict]{type:function, function:{name, description, parameters{…,$defs?}}}
 → (LLM turn) → Sequence[ToolCall]{id, name, arguments:str}
 → GuardDecision{accepted, validated_calls[{tool_call_id, tool_name, arguments:dict}], errors:[]}
   | GuardDecision{rejected, validated_calls:[], errors:[GuardError{…}]}
```

**Approach — catalog builder (decision points):**
- Select server+tool from the policy table only; a missing selected server **or** tool raises
  `MetricResolutionValidationError` before any LLM call — never fall back to another server or
  invent a schema.
- Keep only allowlisted server fields; drop app-owned fields (scrape `url`/`formats`); inject
  app-defined LLM-facing fields (`metric_label`, scrape `id`) as the policy names them.
- For each kept field, if it carries `$ref`, keep the ref and copy the transitively referenced
  `$defs`; then validate every retained `$ref` resolves against the carried `$defs`. If a kept
  field's schema can't be safely carried (unresolvable ref), raise — do not inline, do not
  silently drop.
- Preserve kept fields' types/descriptions/compatible constraints; enforce `search_queries`
  `minItems:1`; set `additionalProperties:false`. If `search_queries` is absent or
  type-incompatible on the raw schema, raise.
- Leave `raw_tool_definitions` unmutated (operate on deep copies).

**Approach — guard (ordered, all-or-nothing):**
1. No calls → single `GuardError(reason_code="no_tool_calls", category=null)`, reject.
2. Each call: required outer fields (`id`, `name`) present and tool-call IDs unique across the
   message → else `invalid_call_structure` (use call position when IDs missing/dup).
3. `name` exact-match against catalog → else `out_of_catalog`.
4. Decode `arguments` JSON string → else `in_catalog` / `invalid_argument_json`.
5. Validate decoded args against that tool's schema (`Draft202012Validator`, error `field_path`
   from the error path) → else `in_catalog`. No coercion/repair/trim/dedup; no blank-string
   checks.
6. If `validation_context is not None` and the selected validator exists and steps 2–5 passed for
   this call: run it; returned issues → `in_catalog` with the issue's `field_path`.
7. Collect **all** detectable errors across all calls; skip a check whose prerequisite failed.
8. Any error ⇒ reject whole message (`validated_calls:[]`), including valid siblings; else accept
   all calls in original order with decoded `arguments`.

## F. Method Detail (non-obvious only)

**`_carry_referenced_defs`** — walk each kept field's schema for `$ref` strings of form
`#/$defs/<name>`; recursively gather referenced `$defs` and their transitive refs; build a
minimal `$defs` dict; assert every collected ref name is present (resolve-check). Failure →
`MetricResolutionValidationError(stage="build_tool_catalog")`. Proves the dry-run's "retained
`$ref` resolves against carried `$defs`" and "raw unchanged" checkpoints.

**`guard_proposed_calls`** — the only deliberate drift responses are structured errors, never
raises; a malformed `tool_catalog` is trusted (it is our own builder's output — see Left-out).

---

## Drift breakdown (per function)

**`build_tool_catalog`**
- Core: controlled function-tool for the context.
- Drifts handled: **Selected server/tool missing** → edge of this abstraction → reject
  (`MetricResolutionValidationError`), no fallback. **`search_queries` absent / type-incompatible
  on raw schema** → reject before LLM call. **Kept `$ref` unresolvable against carried `$defs`** →
  reject (de-mask: fail loudly rather than emit a schema the model can't honor). **Raw schema
  aliasing** → operate on `deepcopy` so `raw_tool_definitions` is never mutated.
- Left out (why): retry/normalize of server descriptions — *not live* (pure derivation).
  Validating the server's *entire* schema semantics — *wrong boundary* (only kept fields matter).
  Inlining `$defs` — *imaginary* benefit, spec forbids it.

**`guard_proposed_calls`**
- Core: accept the whole message iff every call passes, else reject whole.
- Drifts handled: **No calls** → `no_tool_calls`, category null. **Missing outer field /
  duplicate ID** → `invalid_call_structure`, position-based identity. **Out-of-catalog name** →
  `out_of_catalog`. **Malformed arg JSON** → `in_catalog`/`invalid_argument_json`. **Schema-invalid
  args** → `in_catalog` with `field_path`. **`metric_label ∉ set`** (metric contexts,
  `validation_context` supplied) → `in_catalog` via validator; whole message rejected, valid
  siblings withheld. **Dependent-check ordering** → skip a check whose prerequisite failed (no
  cascade noise).
- Left out (why): raising on validation failure — *wrong boundary* (orchestration owns
  replay/retry; the guard returns). Trim/dedup/blank-string/query-count/host-clamp checks —
  *imaginary* (spec explicitly removes them; LLM supplies no URL). Validating `tool_catalog`
  well-formedness — *trust* (our own builder produced it). Execution/budget/cap — *wrong boundary*
  (R3.M1.4).

## Async placement (per async_app_skill)

Both abstractions are **synchronous, on-loop, trivial CPU work** — schema dict manipulation and
in-memory validation that finishes quickly. Per the skill's "trivial CPU work that finishes
quickly runs inline in the coroutine," neither is declared `async`, offloaded to a thread, or
offloaded to a process: the cost of a worker (pool startup, serialization) is not paid for sub-
millisecond dict work, and there is no I/O touchpoint inside either function. The surrounding I/O
(the gateway `open()`/`tools/list`, the LLM `call_turn`, the billed `search_web`) is already
async and awaited by the caller/runner; data dependency is strictly sequential there
(`build → call_turn → guard → execute`), so no concurrency is introduced by this sub-component.

## Logging (per logs_recorder)

One correlation id (`catalog_build_id` / `guard_id`, uuid4) threaded through a function's lines.
- `build_tool_catalog`: INFO `r3m1_1.catalog_built` (context, server, tool, exposed fields,
  `defs_carried` count) — a state change/boundary-out node. On failure the raised
  `MetricResolutionValidationError` carries `stage`; logged once at the caller boundary (not
  re-logged at the throw).
- `guard_proposed_calls`: INFO `r3m1_1.guard_decision` (guard_id, context, decision, `call_count`,
  `error_count`, `reason_codes`, `validator_ran: bool`) — the boundary-out node that lets a
  debugger see why a turn was rejected. No per-call narration; a rejected decision's
  `reason_codes` + `field_path`s are the driving state.
- **Not logged:** argument *values* or `validation_context` contents (avoid payload dumps; metric
  labels can be identifying) — counts and codes only.

---

## Section 4 — Sample Runner & Fixtures

### 4.1 Live sample runner (required)

`feature_sample_runs/r3_m1_1_tool_catalog_guard_sample_run.py`, run from `backend/`:

```bash
python -m src.services.deep_search.feature_sample_runs.r3_m1_1_tool_catalog_guard_sample_run
```

Follows `R3_M1_1_Dry_Run_Traceflow.md` exactly:

- **Harness seeds** (dummy, standing in for the not-yet-built R3.M1.3/R3.M1.5 caller): the
  `context` per pass; a dummy amenity identity + discovery/metric search instructions for the
  message; `validation_context` (`None` for Pass A; `{"metric_labels":["ticket_price",
  "opening_hours"]}` for Pass B); the metric-label validator; the two Pass-B crafted
  proposed-calls fixtures. **Seed inputs must not reuse any prompt worked-pair wording** (R3.M1.1
  has no prompt, so the dummy amenity is a fresh case — a distinct venue, not from the gateway
  runner's capture).
- **Pass A — `website_discovery`, LIVE MCP + LIVE LLM:** `gw.open()` → capture real
  `raw_tool_definitions` → `build_tool_catalog(…, "website_discovery")` → **Checkpoint A1** (only
  web_search; objective+search_queries; no metric_label; kept `$ref` resolves;
  `raw_tool_definitions` deep-equal to captured copy) → real `call_turn()` with the built catalog
  → `guard_proposed_calls(…, validation_context=None)` → **Checkpoint A2** (accepted, order, args
  decoded & preserved, no execution/mutation) → **mandatory 1 billed `gw.search_web(...)`** to
  close the loop → `gw.close()`.
- **Pass B — `metric_web_search`, reuse (no 2nd open):** build catalog once (metric_label now
  required) → **B1** crafted fixture (one valid + one invalid label) ⇒ rejected whole-message,
  valid sibling withheld, error `category:in_catalog`, `field_path:"arguments.metric_label"` →
  **B2** crafted fixture (all valid) ⇒ accepted, order + metric_label preserved. Optional 3rd
  check: B2 fixture with `validation_context=None` still accepts (membership skipped).
- **Optional Firecrawl pass** (only if `FIRECRAWL_API_KEY`): `build_tool_catalog` for `site_map`
  (no LLM-settable args) and `metric_scrape` (candidate `id` + required `metric_label`,
  url/formats absent) against live Firecrawl `tools/list` — catalog-shape assertions only, no live
  scrape.
- **Prints** one titled section per stage (input state, schema, built catalog, provider attempts
  read off `DEEP_SEARCH_LOGGER_NAME` via a collecting handler like the other runners, guard
  decision, executed result). On typed failure: exception class, `stage`, message; non-zero exit.
  Writes nothing to disk.
- **Keys:** `OPENAI_API_KEY`+`GROQ_API_KEY` (live `call_turn`), `PARALLEL_API_KEY` (open + the 1
  billed search). **Cost:** 1 `open()` + 1 LLM turn + exactly 1 billed Parallel search; Pass B
  adds none.

### 4.2 Dummy-provider / fixture pytest set

`feature_tests/test_r3_m1_1_phase_tool_catalog.py` — no live calls. Asserts the code-path rules
the live runner can't prove deterministically:

- **Catalog:** allowlist applied; app-owned fields dropped; `metric_label`/`id` injected per
  context; `additionalProperties:false`; `minItems:1`; `$ref`+transitive `$defs` carried &
  resolve-checked (incl. a crafted raw schema with nested `$defs`); raw definition unmutated
  (deep-equal before/after); missing server/tool and unresolvable `$ref` raise
  `MetricResolutionValidationError`.
- **Guard:** each category fires (`no_tool_calls`, `invalid_call_structure` for missing/dup IDs,
  `out_of_catalog`, `invalid_argument_json`, schema `in_catalog` with `field_path`);
  all-errors-collected (multi-error message); dependent checks skipped on failed prereqs; accept
  preserves order + decoded args with no normalization; whole-message rejection withholds valid
  siblings; `validation_context=None` skips the metric-label validator; invalid label rejects via
  a fake validator.

---

## Architecture & Modularity Decisions

### Layer 1 — Glance
- **Shape:** two reusable pure functions in one module, parameterized by a context policy table;
  consumed later by R3's stage methods and any other tool-turn caller.
- **Seams:** *context policy* — which server/tool/fields per context, changes as new evidence
  phases are added; *additional validator* — runtime data-dependent checks, swappable by
  tool+context; *JSON-schema validation* — delegated to `jsonschema`.
- **Components:** `build_tool_catalog` — MCP schema → controlled function-tool ·
  `guard_proposed_calls` — whole-message validation · `AdditionalValidator` — runtime membership
  checks · `metric_label_membership_validator` — the one impl.

### Layer 2 — Component Map
| Component | Owns | Depends on | Abstracted? |
|---|---|---|---|
| `build_tool_catalog` | schema derivation per context | `RawToolDefinition`, policy table | — (concrete fn) |
| `guard_proposed_calls` | message validation + decision | `ToolCall`, `jsonschema`, validator | — (concrete fn) |
| `AdditionalValidator` | runtime value-check contract | — | Yes: data-dependent checks vary by tool+context, selected at runtime |
| `metric_label_membership_validator` | label∈set check | `AdditionalValidator` | implements |

### Decisions & Justifications (what breaks today without it)
| Decision | Current requirement that forced it | What breaks today without it |
|---|---|---|
| `AdditionalValidator` Protocol | metric contexts need label-membership vs runtime set; discovery needs none | guard hard-codes metric logic; `website_discovery` can't skip it; B1/B2 can't vary by `validation_context` |
| Context policy **table** (not per-context functions) | spec defines 4 contexts, same build/guard algorithm | each new phase (R3.M1.4) copies the build/guard code instead of adding a row |
| Module-level **functions** (not class methods) | spec: reusable by any caller, dry-run calls them free-standing | binding to `SpecificMetricResolution` blocks reuse and forces a `self` that holds no needed state |

### Kept Concrete / Rejected
| Considered | Decision | Reason |
|---|---|---|
| Catalog/guard as `SpecificMetricResolution` methods | rejected | no caller yet; spec requires cross-responsibility reuse |
| `ToolCatalog`/`GuardInput` wrapper classes | rejected | `list[dict]` is the exact shape `call_turn` already consumes; a wrapper adds a hop with no consumer needing it |
| Per-tool validator interface in `clients/` | kept in `phase_tool_catalog` | validators read R3 runtime facts; `clients/` must not import `services/` |
| New guard error base-exception class | rejected | guard returns `GuardDecision`, never raises; only catalog-construction raises (reuses `MetricResolutionError` family) |

### Dependency Direction
```
phase_tool_catalog → RawToolDefinition, RawToolDefinitions   (clients/mcp_tools)
phase_tool_catalog → ToolCall                                 (clients/llm_provider)
phase_tool_catalog → [AdditionalValidator] ← metric_label_membership_validator
later R3 stage methods → phase_tool_catalog (functions)
```

### Composition Root
No new wiring. The functions are stateless; the existing `create_specific_metric_resolution` /
`create_deep_search` roots are unchanged. The sample runner and, later, R3.M1.3/R3.M1.4 call the
functions directly.

### End-to-End Flow
1. Caller (runner now; R3.M1.3 later) obtains `raw_tool_definitions` from the gateway and picks a
   `context`.
2. `build_tool_catalog` returns the controlled function-tool list.
3. Caller sends it as `tools` to `StructuredLLMCaller.call_turn`; gets `AssistantTurn.tool_calls`.
4. `guard_proposed_calls` returns one `GuardDecision`; accepted calls flow to future execution
   (R3.M1.2/.4), rejected to future rejection/replay handling (R3.M1.1 steps 3–4).

---

## Cross-mechanism check (feature_context)

- **Implemented upstream mechanisms need no code change.** R3.M1.1 consumes the already-built
  C3.1.1 gateway (`get_tool_definitions`, `RawToolDefinition`) and C3.1.2 caller (`call_turn`,
  `ToolCall`, `AssistantTurn`) exactly as they stand. The spec's "Prerequisites" (RC10
  `resolution_source`, Mechanism-6 verification-text, Mechanism-1.3 renames) are **R3.M2**
  dependencies, not R3.M1.1 — none gates this sub-component.
- **Doc-only drift (not a build todo):** `deep_search_context.md` still labels this sub-component
  `C3.1.3` (and the discovery caller as `C3.1.5`), predating the R3 promotion/rename in the spec.
  The spec is the newer canonical source. Per the rule that the Build checklist excludes writing
  canonical markdown, this is flagged rather than folded into the build — apply as a separate pass
  if desired.

---

## Build checklist (todos, executed only after acceptance)

1. Add `MetricResolutionValidationError` to `exceptions/deep_search.py`.
2. Create `phase_tool_catalog.py`: `ToolContext`, `_CONTEXT_POLICY`/`_Policy`, contracts
   (`GuardDecision`, `ValidatedCall`, `GuardError`, `ValidationIssue`, `AdditionalValidator`).
3. Implement `build_tool_catalog` + helpers (`_select_definition`, `_derive_controlled_schema`,
   `_carry_referenced_defs`, `_adapt_to_function_tool`) with logs.
4. Implement `guard_proposed_calls` + `_schema_by_tool_name`/`_validator_for` +
   `metric_label_membership_validator` with logs.
5. Write the live sample runner `r3_m1_1_tool_catalog_guard_sample_run.py` (Section 4.1).
6. Write the dummy-provider fixture pytest set (Section 4.2).

> The checklist excludes writing the two canonical markdown files and excludes executing any todo
> during planning.
