# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.1 (MCP Tool Gateway), Iteration 6

**Status:** Iteration 6 implemented. Verification results are recorded below; the appended iteration report remains the original planning record.

**Scope:** extend the current gateway with session-scoped raw tool definitions using finalized Approach A: retain definitions during `open()`, expose a synchronous deep-copy getter, and preserve server grouping. The iteration report was completed first and replaces the previous report at the end of this file. This revision consolidates the previous plan's historical sections around the current iteration-5 baseline; superseded batch/probe machinery is not pending build work.

**Sources:** C3.1.1 in `deep_search_context.md`; the preceding implementation plan; the user's attached new requirements and chat decisions. Planning skills applied: `skills/iteration_report.md`, `Implementation_architecture_skill.md`, `Plan_output_format.md`, `async_app_skill.md`, `drift_analyzer.md`, `logs_recorder.md`, and the architecture format referenced by the plan-format skill. Per the user's instruction, architecture and report remain in this existing file; no separate planning file is created.

## Iteration point to plan section

Report IDs are scoped to the appended report. Existing plan IDs A1–A7, M1–M13 and R1–R4 describe previous work and are not reused.

| Plan ID | Report ID | Class | Change | Where |
| --- | --- | --- | --- | --- |
| A8 | A1 | ADD | Local accessor with deep-copy isolation | B–H; todos 5, 9, 10, 12, 13 |
| A9 | A2 | ADD | Server grouping and caller handoff | B–F; todos 5, 9–13 |
| M14 | M1 | MODIFY | Preserve all full raw definitions | B–H; todos 5, 9–13 |
| M15 | M2 | MODIFY | Session snapshot publication and invalidation | B–H; todos 4, 5, 9, 10, 12, 13 |

## Decisions and boundaries for this revision

| Topic | Finalized rule |
| --- | --- |
| Retrieval | Use the existing opening-time listing pass on each server. |
| Public API | Keep async `open() -> None`; add synchronous `get_tool_definitions()`. |
| Stored scope | Retain every listed tool, not only the currently used tools. |
| Server identity | Outer keys are application-owned `parallel` and `firecrawl`. |
| Collision handling | Same tool name on different servers occupies separate inner dictionaries. |
| Schema fidelity | Preserve complete input schemas; C3.1.3 derives restricted copies. |
| Ownership | Getter deep-copies nested objects; workflow state owns the returned copy. |
| Snapshot lifetime | Publish only after both listings and capability checks succeed. |
| Refresh | No refresh during an open session, including explicit re-verification. |
| Invalid lifecycle access | Raise existing `McpConnectionError(stage="get_tool_definitions")`. |
| Workflow handoff | Later orchestrator stores the grouped result before discovery begins. |
| Catalog selection | Context policy selects server plus tool; no implicit server fallback. |
| Execution scope | Definition retention does not add a generic tool execution method. |

The lifecycle-error class/stage, frozen dataclass representation, and lifecycle serialization below are implementation choices that realize the finalized contract. They are not new product requirements. The requested Testability bullet is excluded from these decisions; verification remains in the existing plan's dedicated section.

## Existing behavior preserved

| Area | Current baseline retained |
| --- | --- |
| Ownership (D1) | One owner task per server enters/exits the SDK context; never replace a live session on timeout. |
| Transport (D2, M5) | `httpx2.AsyncClient`; timeout connect 10 s, read unbounded, write/pool 10 s. |
| SDK boundary | Only `clients/mcp_tools.py` imports MCP types; callers receive application contracts. |
| Connect requirements | Parallel `web_search(objective, search_queries)`; Firecrawl map `url`, scrape `url/formats`. |
| Optional operations | Crawl/status are retained but not required at connect. |
| Removed machinery | No MCP batch resolver, batch-job polling, or connection-time Firecrawl shape probe. |
| Fan-out (M13) | `scrape_pages` concurrently uses `scrape_page`; per-URL failures populate `failed_urls`. |
| Firecrawl controls (A7) | One shared semaphore of 2 and rate bucket of 10/min per gateway instance. |
| Parallel controls | Search semaphore of 4; no Firecrawl rate token. |
| Timeouts | Search 30 s; map/scrape 60 s; crawl call 60 s, total 180 s, poll 3 s. |
| Token waits | Pacing waits remain outside the live-call timeout. |
| Retry (M6–M8) | Timeout/transport waits 2 then 3 s; rate limits honor Retry-After, else 30 then 60 s. |
| Result decode | Prefer SDK `structured_content`, then JSON text; bad shapes become `unparseable`. |
| Map result | Read links as objects, tolerate legacy strings; empty links remain valid. |
| Scrape result | Read top-level markdown and metadata.sourceURL; missing sourceURL fails parsing. |
| URL ownership | Application supplies URLs; host policy, candidate IDs and metric labels belong above the gateway. |
| Retained config | `firecrawl_probe_url` remains accepted but unused; do not restore the probe. |
| Input failures | Existing empty/invalid argument `ValueError` behavior remains. |

These are carried-forward implementation decisions, not newly verified vendor limits. The account's actual limit/window behavior remains an open verification item.

## 0. Cross-mechanism check

| Piece | Finding | Action |
| --- | --- | --- |
| `AmenitySearch` | Gateway injection and closure already exist. | No new responsibility class or workflow stage. |
| M1-only tests/sample | Inject `None` for the unused gateway. | Leave unchanged. |
| C3.1.2 | Receives function-tool definitions, not raw MCP schemas. | Leave provider caller and request modes unchanged. |
| C3.1.3 | Its input table still specifies a flat raw-definition dictionary. | Plan #11 updates the input and source-selection policy. |
| C3.1.7 | Workflow-state owner is not implemented here. | Specify the handoff; do not invent a state model in the gateway. |
| Sample runner | `_stage_open` re-lists both servers after opening. | Replace private reads with the new accessor. |
| Existing gateway fakes | No Python fake implementing `ToolGateway` found in inspected workflow tests. | Extend any actual protocol fake encountered; do not create a new fake hierarchy. |
| Exception docs | Still refer to the removed connection-time probe. | Correct docs while adding the accessor lifecycle stage. |

## 1. File and Module Structure (Build todos)

Todos retain their original numbers so report artifact references remain stable. All paths are repository-relative. The following table records the iteration-6 implementation scope.

| # | File | Action | Ownership |
| --- | --- | --- | --- |
| 1 | `backend/requirements.txt` | No change | Existing MCP/httpx2 dependencies suffice. |
| 2 | `backend/src/core/config.py` | No change | Existing keys, URLs and unused probe setting. |
| 3 | `backend/.env.example` | No change | No new environment configuration. |
| 4 | `backend/src/exceptions/mcp.py` | Modify docs | Existing lifecycle error family and stages. |
| 5 | `backend/src/clients/mcp_tools.py` | Modify | Definition contract, retention, getter, lifecycle and boundary logs. |
| 6 | `backend/src/services/deep_search/amenity_search.py` | Check only | Preserve gateway injection and ownership. |
| 7 | Existing place/accessibility/result-attachment tests | No change | M1-only callers still inject `None`. |
| 8 | `backend/src/services/deep_search/feature_sample_runs/result_attachment_sample_run.py` | No change | Existing M1-only sample. |
| 9 | `backend/tests/services/deep_search/test_mcp_tool_gateway.py` | Modify | Offline gateway contract and regression cases. |
| 10 | `backend/src/services/deep_search/feature_sample_runs/mcp_tool_gateway_sample_run.py` | Modify existing runner | Public snapshot read and grouped handoff display. |
| 11 | `backend/src/services/deep_search/feature_context/deep_search_context.md` | Modify docs at build | C3.1.1 requirement and C3.1.3 grouped input contract. |
| 12 | `backend/src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py` | Modify | Component harness covers the same public contract. |
| 13 | `backend/src/services/deep_search/feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` | Modify docs | Record definition and lifecycle acceptance criteria. |

Keep definition types next to existing result contracts in #5. The gateway must not import `services/` schemas. No new source, sample, architecture, or report file is needed. The existing live sample is reused; a new LLM call would not exercise this MCP-only capability.

## A. Feature Map

```text
Feature: Deep Search
└─ FeatureClass: DeepSearch
   └─ Responsibility: AmenitySearch
      └─ Mechanism 3 workflow: run_llm_metric_resolution (later)
         └─ C3.1 evidence acquisition (later)
            └─ C3.1.1: ToolGateway capability, implemented by McpToolGateway
               ├─ Setup stage: open sessions, list and verify capabilities
               │  └─ Retain complete definitions grouped by server
               ├─ Handoff capability: get_tool_definitions
               │  └─ Local deep copy for later workflow setup
               ├─ Execution stages: search, map, scrape, multi-page scrape
               ├─ Retained operation: crawl and status re-read
               └─ Teardown stage: invalidate definitions and close sessions
```

Definition capture is part of the existing setup mechanism. The accessor is a handoff capability, not a new responsibility workflow. No catalog builder, generic tool executor, or workflow coordinator is added to C3.1.1.

## B. Data Contracts

| Contract | Fields / meaning | Mutability | Created by / read by |
| --- | --- | --- | --- |
| `RawToolDefinition` [M14] | `name: str`; `description: str \| None`; `input_schema: dict[str, Any]` | Frozen dataclass; nested schema is mutable | Listing adapter / getter and C3.1.3 |
| `RawToolDefinitions` [A9] | Alias for `dict[str, dict[str, RawToolDefinition]]` | Nested dictionaries | Verified setup / workflow state |
| Server keys [A9] | Exactly `parallel` and `firecrawl` for these two gateway roles | Stable application identity | Gateway wiring / catalog context policy |
| Private snapshot [M15] | `_raw_tool_definitions: RawToolDefinitions \| None` | Gateway-owned, replaced only at lifecycle boundaries | Successful open / getter |
| Listing candidate [M14] | `dict[str, RawToolDefinition]` for one server | Local setup data until publication | `_list_tools` / verifier |
| `McpServerConfig` | Name, URL, nullable key, call timeout | Existing frozen dataclass | Factory / gateway |
| `WebSearchResult` | Objective, queries, excerpts, retrieved timestamp | Existing frozen dataclass | Search / caller |
| `MapResult`, `MapLink` | Homepage and typed candidate links | Existing frozen dataclasses | Map / caller |
| `ScrapeResult` | Source URL, markdown text, retrieved timestamp | Existing frozen dataclass | Single scrape / caller |
| `ScrapeResults` | Successful pages, total/completed, failed URLs, timestamp | Existing frozen dataclass | Fan-out / caller |
| `CrawlResult`, `CrawledPage` | Job identity and typed crawled pages | Existing frozen dataclasses | Retained crawl / caller |
| `ToolFailure` | Tool, failure kind, message | Existing frozen dataclass | Execution / caller |
| `McpGatewayError` family | Existing connection and unavailable errors with stage | Exceptions | Setup/access / caller |

A frozen dataclass does not freeze its nested schema. Use a deep copy both when converting the SDK definition into the application contract and when returning the snapshot. Preserve the schema exactly, including empty schemas, nested dictionaries/lists, constraints, required fields, descriptions, references, and transitive definition content. Do not prune unused tools or schema keywords.

The getter returns data equivalent to the stored snapshot, not the original SDK response object. Closing clears the gateway-owned snapshot; a copy already stored in workflow state remains an independent object. The workflow owner must discard or replace that copy when its run ends or a new session begins.

### Caller contract

| Context | Selected outer key | Selected inner key |
| --- | --- | --- |
| `website_discovery` | `parallel` | `web_search` |
| `metric_web_search` | `parallel` | `web_search` |
| `site_map` | `firecrawl` | `firecrawl_map` |
| `metric_scrape` | `firecrawl` | `firecrawl_scrape` |

C3.1.3 accepts the grouped type, checks the selected server/tool, and transforms copies. Missing selections or incompatible transformations fail catalog construction before an LLM request. This source policy is a contract update, not gateway-side catalog logic.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementation / consumer |
| --- | --- | --- | --- |
| `ToolGateway` | Existing Protocol | Existing async lifecycle/operations plus sync getter | `McpToolGateway`; workflow callers |
| `ClientFactory` | Existing callable alias | Config to async context manager yielding SDK Client | HTTP production / in-process fixtures |
| `_ServerSession` | Concrete private owner | Start, obtain client, stop in owning task | Gateway |
| `mcp.Client` | External dependency | List tools, call named tool | Adapter only |
| `RawToolDefinition` | Application contract | SDK-independent name, description and schema | Gateway and catalog builder |
| `RawToolDefinitions` | Type alias | Server-grouped definition dictionaries | Gateway and workflow state |
| `Settings` | Existing configuration | Keys, URLs and retained probe setting | Factory only |

Extend the existing Protocol instead of introducing a second catalog interface. The data alias adds no runtime wrapper.

## D. Class & Method Blueprint

Signatures use planned names consistently. Async methods are marked; mutation and failures are explicit. New private state is limited to the snapshot, one lifecycle lock, and one session correlation identifier for definition-boundary logs.

### McpToolGateway

| Method | Signature | Purpose |
| --- | --- | --- |
| Constructor | `__init__(parallel: McpServerConfig, firecrawl: McpServerConfig, ...) -> None [mutates: self]` | Initialize sessions, limits, unavailable snapshot and lifecycle lock. |
| Open, async [M15] | `open() -> None [mutates: self._raw_tool_definitions] [raises: McpGatewayError]` | Open and publish one complete verified session snapshot. |
| Start sessions, async | `_start_sessions() -> None [raises: McpConnectionError]` | Start both independent session owners. |
| Verify, async [M14, M15] | `verify_capabilities() -> RawToolDefinitions [raises: McpGatewayError]` | Return verified definitions without refreshing an open session. |
| List, async [M14] | `_list_tools(session: _ServerSession) -> dict[str, RawToolDefinition] [raises: McpGatewayError]` | Convert a complete server listing into owned definitions. |
| Require [M14] | `_require(catalog: dict[str, RawToolDefinition], tool: str, arguments: Sequence[str], server: str) -> None [raises: McpToolUnavailableError]` | Check existing required names against preserved input schemas. |
| Getter, sync [A8, A9] | `get_tool_definitions() -> RawToolDefinitions [raises: McpConnectionError]` | Return a deep copy of the available grouped snapshot. |
| Search, async | `search_web(objective: str, search_queries: Sequence[str]) -> WebSearchResult \| ToolFailure` | Search through the existing bounded retry path. |
| Map, async | `map_site(url: str) -> MapResult \| ToolFailure` | Map the application-supplied homepage into typed links. |
| Scrape, async | `scrape_page(url: str) -> ScrapeResult \| ToolFailure` | Scrape one application-supplied URL into typed markdown. |
| Fan-out, async | `scrape_pages(urls: Sequence[str], *, formats: Sequence[str] = ("markdown",)) -> ScrapeResults \| ToolFailure` | Gather independent single-page scrapes with per-URL failure attribution. |
| Crawl, async | `crawl_site(url: str, limit: int, depth: int) -> CrawlResult \| ToolFailure` | Retain crawl submission and same-job status recovery. |
| Close, async [M15] | `aclose() -> None [mutates: self._raw_tool_definitions]` | Invalidate definitions before stopping both session owners. |

Existing execution methods keep their current input/lifecycle raises, `ValueError` and `McpConnectionError`. No execution signature or result contract changes.

### Supporting implementation

| Owner / methods | Change |
| --- | --- |
| `ToolGateway.open`, `aclose`, typed operations | Keep the existing protocol signatures. |
| `ToolGateway.get_tool_definitions` | Add synchronous grouped-definition return contract. |
| `_ServerSession.start/client/stop/_run/_await_task` | Unchanged same-task SDK context ownership. |
| `_call_with_retry`, `_single_call` | Unchanged retry, semaphore and Firecrawl token behavior. |
| `_read_crawl_job` | Unchanged deadline and same-job polling. |
| `_parse_search_result`, `_parse_map_result`, `_parse_scrape_result` | Unchanged typed parsing. |
| `_parse_crawl_result`, `_parse_crawl_status`, `_decode_body` | Unchanged parsing and structured-content preference. |
| `_classify_failure`, `_log_attempt` | Unchanged execution classification and retry diagnostics. |
| `_TokenBucket.acquire` | Unchanged async pacing on the shared Firecrawl path. |
| `_streamable_http_factory` | Unchanged async-native HTTP transport and bearer handling. |
| `create_mcp_tool_gateway(settings: Settings) -> McpToolGateway` | Unchanged composition root; opens nothing. |

## E. Runtime Flow: Data Object Journey

The definition setup/handoff precedes the existing evidence-execution path. Rows belonging to later components are labeled; runner and fixtures are excluded.

| # | Stage / capability | Reads | Produces / mutates |
| --- | --- | --- | --- |
| 1 | Await `open` | Configured server sessions | Serialize lifecycle setup; definitions unavailable. |
| 2 | Await `_start_sessions` | Both configs | Two live SDK session owners. |
| 3 | Await verifier and listing helpers | Independent server listings | Local full-definition dictionaries. |
| 4 | Existing required-capability checks | Local schemas | Verified grouped candidate or typed error. |
| 5 | Successful `open` completion | Verified candidate | Publish private snapshot; return `None`. |
| 6 | Sync `get_tool_definitions` | Private snapshot | Independent deep copy, grouped by server. |
| 7 | Orchestrator handoff (later) | Returned copy | Assign `workflow_state.raw_tool_definitions` once. |
| 8 | Catalog builder (C3.1.3, later) | Grouped definitions and context | Restricted copied catalog; raw state unchanged. |
| 9 | Existing guard/execution (later caller) | Admitted arguments | Existing typed operation result or `ToolFailure`. |
| 10 | Await `aclose` | Snapshot and sessions | Definitions unavailable; owner tasks stopped. |

**Shape trace:**

```text
Parallel SDK listing             Firecrawl SDK listing
       ↓                                ↓
{tool_name: RawToolDefinition}    {tool_name: RawToolDefinition}
       ↓                                ↓
RawToolDefinitions {
  parallel: {tool_name: {name, description, input_schema: complete JSON Schema}},
  firecrawl: {tool_name: {name, description, input_schema: complete JSON Schema}}
}
       ↓ verified and published as gateway-private snapshot
       ↓ getter deep-copies every nested schema object
workflow_state.raw_tool_definitions: RawToolDefinitions (later owner)
       ↓ context selects source server and tool; derives another copy
tool_catalog: list[function-tool definitions] (C3.1.3)
```

A setup failure never reaches rows 5–9. The orchestrator handles the gateway exception before discovery. Catalog failures stop before the LLM call; tool execution retains its existing per-call failure behavior.

## F. Method Detail

### `__init__` [M15]

- **Purpose:** establish unavailable definition state without opening sessions.
- **Approach:** add a nullable private snapshot and a lifecycle lock; retain all existing configs, limits and factory wiring.
- **Input/output:** existing constructor parameters; initialized gateway.
- **Failure:** no new dependency calls or configuration errors.

### `open` [M15]

- **Purpose:** publish definitions only for fully successful setup.
- **Approach:** serialize with `aclose` using one lifecycle lock. If already successfully open, return without listing again. Otherwise begin a new setup correlation ID, leave snapshot unavailable, start sessions and obtain the verified local candidate.
- Publish the candidate only after all checks pass, with no intervening await before successful completion.
- Any setup error or cancellation leaves the snapshot unavailable, closes both owners and propagates the original failure. Keep cleanup inside the lock; do not recursively call the lock-taking public `aclose` from this path.
- **Input/output:** no arguments; returns `None`.
- **Failure:** existing gateway errors or propagated cancellation. No partial success.

### `_list_tools` [M14]

- **Purpose:** adapt complete SDK definitions at the infrastructure boundary.
- **Approach:** retain the existing initial listing behavior with SDK cache bypassed. Convert every returned tool to the application contract, preserving nullable descriptions and a deep copy of the complete input schema.
- Do not fall back to an invented empty schema for a malformed/missing schema. Trust the SDK's decoded mapping contract; if adapter conversion detects a violation, reject with `McpToolUnavailableError(stage="verify_capabilities")` naming server/tool.
- Determine the SDK's pagination behavior at build time. If it already aggregates pages, reuse it. If a continuation is exposed, consume it as part of this initial listing pass; do not publish a truncated catalog.
- Keep the existing per-server `mcp.tools_listed` boundary summary; derive its argument-name summaries from the preserved schemas.
- **Input/output:** one session; owned per-server definitions.
- **Failure:** preserve current listing-error translation to `McpConnectionError`; no broad new retry mechanism.

### `verify_capabilities` and `_require` [M14, A9, M15]

- **Purpose:** check current required capabilities against complete definitions.
- **Approach:** when the open-session snapshot exists, check/read that snapshot and return an independent copy without re-listing. The initial setup path obtains both per-server results concurrently as local return values, then checks and groups them.
- Associate results with fixed application roles `parallel` and `firecrawl`, not configured display names or tool-name inference.
- `_require` reads top-level property names from the retained schema and applies exactly the existing tool/argument checks. Schema transformation compatibility is C3.1.3's responsibility.
- Return a verified grouped candidate to `open`; this helper does not publish availability. The helper is a concrete setup method, not part of `ToolGateway`. External workflow callers use `open` and the getter, not this helper as an alternate lifecycle.
- Collect both listing outcomes before raising the first failure, so no sibling listing remains outstanding during teardown; cancellation also cancels and settles both listing tasks before cleanup.
- **Input/output:** no arguments; `RawToolDefinitions`.
- **Failure:** existing connection or unavailable errors; required crawl/status/batch checks are not added.

### `get_tool_definitions` [A8, A9]

- **Purpose:** expose an isolated local snapshot to callers.
- **Approach:** require an available successful-open snapshot, then deep-copy the entire nested structure. Do not refresh, filter by context, mutate the snapshot, or call a server.
- **Input/output:** no arguments; `RawToolDefinitions`.
- **Failure:** `McpConnectionError(stage="get_tool_definitions")` before opening, during unfinished setup, on failed setup, or after invalidation.
- This short in-memory operation stays synchronous. A caller that retains a copy cannot use the getter to infer whether that older copy still belongs to a live session.

### `aclose` [M15]

- **Purpose:** invalidate definition availability and end session ownership.
- **Approach:** acquire the lifecycle lock, clear the snapshot before awaiting session shutdown, then stop both owners through the existing cleanup path. Repeated closing remains harmless.
- **Input/output:** no arguments; `None`.
- **Failure:** preserve existing owner-stop behavior; invalidation remains effective if cleanup raises or is cancelled.

## G. Drift entries (per changed method)

Scanned input, inherited state, dependencies, concurrency, resources, time and completion. The guards below follow explicit requirements or silent data-loss paths visible in the current reduction/copy design. Do not introduce shape-tolerant parsing for hypothetical server variants.

### `__init__`

**Core behavior:** construct an unavailable snapshot and lifecycle synchronization.

**Drifts handled:** eager definition availability would expose unverified data; caught in gateway state initialization; reject access until publication by using `None`.

**Left out (why):** new config validation and persistent cache construction are not needed; existing wiring is trusted and persistence is not a requirement.

### `open`

**Core behavior:** start both owners and publish one completely verified snapshot.

**Drifts handled:**

- One listing/check fails after the other succeeds; caught at setup completion; reject publication, close both owners and propagate.
- Cancellation interrupts setup; caught by existing non-local-exit cleanup; invalidate and propagate after owner cleanup.
- Repeated opening could refresh an existing session silently; caught by lifecycle state; return unchanged when already open.
- Open/close interleave around awaits and could publish stale definitions after closing; caught by one lifecycle lock; serialize lifecycle mutations.

**Left out (why):** automatic session replacement remains rejected by D1; partial Parallel-only operation contradicts the required two-server setup; distributed lifecycle locks are not live for an event-loop-local gateway.

### `_list_tools`

**Core behavior:** return every full definition from one listing pass.

**Drifts handled:**

- Argument-set reduction silently destroys schema constraints/references; caught at the SDK adapter boundary; retain complete definitions instead.
- SDK/caller objects alias nested schemas; caught at adaptation; deep-copy into application ownership.
- Listing fails; caught by existing error translation; propagate the typed connection failure.
- Invalid schema representation must not appear as valid empty data; caught at adapter conversion if the SDK permits it; reject explicitly rather than inventing a schema.

**Left out (why):** arbitrary schema-dialect repair belongs to catalog construction; full JSON Schema validation of unused tools is outside this boundary; pagination API details are an open SDK check, not grounds to invent an unsupported cursor API.

### `verify_capabilities`

**Core behavior:** group complete catalogs and verify the existing required set.

**Drifts handled:**

- Cross-server names collide in a flat dictionary; caught at grouped assembly; preserve both under their fixed server roles.
- A required tool/argument disappears; caught by `_require`; reject using the existing unavailable error.
- One concurrent listing fails while its sibling is still running; caught by setup collection; settle both before propagation and cleanup.
- Explicit verification re-fetches definitions mid-session; caught by snapshot availability; reuse stored definitions.

**Left out (why):** implicit search on another server is forbidden by the agreed source policy; same-name duplicates within one server have not been observed and the SDK/server name contract is trusted; catalog field allowlists are C3.1.3's boundary.

### `_require`

**Core behavior:** preserve existing mandatory tool/argument checks.

**Drifts handled:** required argument missing from the full schema; caught at the same capability boundary; reject with server/tool/argument context.

**Left out (why):** validation of field types and reference-safe transformations belongs to C3.1.3; adding crawl or batch requirements would reverse settled scope.

### `get_tool_definitions`

**Core behavior:** return one independent grouped snapshot without I/O.

**Drifts handled:**

- Access before successful opening or after invalidation; caught at accessor entry; reject with the chosen lifecycle error.
- Shallow-copy aliases permit caller edits to change later catalogs; caught at the return boundary; deep-copy nested schemas and both dictionary levels.
- A caller edits one returned copy; gateway-owned data stays unchanged and subsequent reads return equivalent raw definitions.

**Left out (why):** automatic refresh and stale-copy revocation are outside this API; getter locking is unnecessary because it has no await and lifecycle mutation uses the same event loop; speculative worker pools and size limits need measured evidence.

### `aclose`

**Core behavior:** clear availability before stopping session owners.

**Drifts handled:** teardown awaits or fails while old definitions remain readable; caught before the shutdown await; invalidate first and preserve cleanup/cancellation signaling. Concurrent lifecycle writers are serialized by the existing iteration's lifecycle lock.

**Left out (why):** mutating caller-held copies would break ownership isolation; repeated invalidation is harmless and does not need a second cleanup strategy.

## H. Logging

Use the existing `DEEP_SEARCH_LOGGER_NAME` JSON stream. Keep current execution events and redaction behavior. Add only the fields/events needed to connect the new definition boundary with snapshot lifetime; do not dump full schemas or log getter success.

| Event | Level | Node | Driving fields / behavior |
| --- | --- | --- | --- |
| `mcp.tools_listed` | INFO | Existing external boundary | Keep server, tool_count, tools, args; add stable server_key and gateway_session_id. |
| `mcp.tool_definitions_state` | INFO | Shared-state transition | gateway_session_id, available, counts_by_server, reason. |
| Existing caller failure handling | ERROR | Rejection endpoint | Error class, stage and server/tool context; log once where handled. |
| Existing execution events | Unchanged | Retry/degrade/boundary | Preserve call failures, skipped map links and partial scrape results. |

The setup identifier is an opaque per-open correlation value, not an API key or MCP session credential. Generate it before initial listings and reuse it for their boundary summaries and snapshot publication/invalidation. Successful publication and invalidation of a published snapshot each earn one state event; repeated getter reads and repeated no-op close do not. Failed setup has no published snapshot transition; its rejection rides the exception and listing summaries.

No schema bodies, tool-description text, bearer headers, or serialized config objects are logged. Source/schema compatibility errors carry only actionable server/tool/field identifiers. Later orchestration may bind its run correlation context without adding a gateway dependency on amenity identity.

## 4. Sample Runner and Fixture Set

### 4.1 Existing live sample runner

Modify #10 rather than creating a second runner. From `backend/`, the existing command is `python -m src.services.deep_search.feature_sample_runs.mcp_tool_gateway_sample_run`.

| Stage | Planned output |
| --- | --- |
| Existing input state | Seed amenity/website as before; do not call earlier mechanisms. |
| Open | Existing connection and capability summaries. |
| New definition handoff display | Getter result grouped by server; tool names/counts and one selected schema's field summary. |
| Dummy workflow state | Demonstrate assignment to raw_tool_definitions using the same grouped contract. |
| Existing operations | Keep search/map/scrape/scrape_pages and opt-in crawl stages. |
| Close | Existing owner shutdown display; accessor after close reports its typed lifecycle error if demonstrated. |

Replace `_stage_open`'s direct reads of private server clients with the accessor. Apply the same definition display to the scrape-only opening path without adding a listing or search call. Preserve `--v2a`, `--v2b`, `--crawl`, `--scrape-only`, URL and tracing flags. Correct stale batch wording in touched help text if encountered.

No LLM call is added: catalog construction and tool turns are later components. The new definition display requires live listings only; the existing runner's subsequent operations still consume vendor resources. No live sample was executed for this documentation task.

### 4.2 Offline fixture coverage

Extend both existing gateway test files (#9 and #12) and the test plan (#13). Reuse in-process servers or focused recording clients; do not add a new fixture framework.

| Contract | Observable assertion |
| --- | --- |
| Full fidelity | Nested required/enum/array constraints and reference chains survive unchanged. |
| Nullable description | Missing description is retained as None. |
| Retained tool scope | Unused listed tools remain present in their source group. |
| Grouping | Same tool name on two servers preserves both distinct schemas. |
| SDK ownership | Modifying the source fixture object cannot change the retained snapshot. |
| Deep-copy return | Editing nested dictionaries/lists in one result leaves later results unchanged. |
| Network reuse | Getter reads, repeated open, and explicit re-verification add no listing calls in an open session. |
| Opening failure | One server/listing/check failure yields no readable partial snapshot. |
| Cancellation | Mid-open cancellation settles setup work and leaves definitions unavailable. |
| Lifecycle | Before open, during setup and after close use the named lifecycle error/stage. |
| Close serialization | Close queued behind opening leaves definitions unavailable when that close completes. |
| Session reset | A later successful session gets a new snapshot; old caller-held copies remain independent. |
| Capability regression | Missing search/map/scrape arguments still fail; optional crawl absence still passes. |
| Diagnostic behavior | Boundary/state events share setup identity; getter reads emit no success noise. |
| Existing execution | Relevant retry, parsing, fan-out, pacing, ownership and key-hygiene cases continue passing. |

Assertions measure contract behavior, not calls to the copying implementation. List-count checks count initial listing passes or actual page requests according to verified SDK pagination behavior.

## Architecture and Modularity Decisions

### Layer 1: Glance

**Shape:** the existing concrete gateway retains definitions behind its existing Protocol.

- MCP SDK boundary: adapt server objects into application-owned definitions.
- Workflow boundary: return copies; later callers own state and catalog policy.
- Lifecycle boundary: one successfully opened session owns one definition snapshot.

| Component | Ownership |
| --- | --- |
| ToolGateway | Typed execution plus definition-reading contract. |
| McpToolGateway | SDK adaptation, snapshot lifetime and isolated reads. |
| RawToolDefinition / grouped alias | Definition shape and server identity. |
| Later orchestrator / catalog builder | Workflow state, context selection and restricted schemas. |

### Layer 2: Justification

| Decision | Current requirement | What breaks without it |
| --- | --- | --- |
| Extend existing Protocol | Callers need definitions without SDK imports. | Workflow couples to private MCP sessions. |
| Application-owned frozen dataclass | Preserve typed raw definition fields. | SDK objects leak above the client boundary. |
| Grouped dictionary alias | Preserve each server's tool namespace. | Same-name definitions overwrite each other. |
| Private snapshot in gateway | Reuse definitions for an entire open session. | Re-listing can change schemas between turns. |
| Deep-copy boundary | Caller transformations must not change raw definitions. | Nested mutations corrupt later catalogs. |
| One lifecycle lock | Setup/teardown await while touching shared availability. | Close/open interleaving can publish stale state. |

**Over-engineering guard:** no new interface, service layer or factory is introduced. The existing Protocol has a current caller-independence requirement. The dataclass is a value contract, the alias has no runtime layer, and the single lock protects one asynchronous lifecycle boundary.

| Considered | Decision | Reason |
| --- | --- | --- |
| Separate schema service/interface | Rejected | One gateway already owns the listing boundary. |
| Return definitions from open | Rejected | User finalized the separate getter. |
| Lazy async retrieval | Rejected | Listing already occurs during setup. |
| Flat merge plus collision rejection | Rejected | Agreed grouping preserves both source namespaces. |
| Generic MCP executor | Rejected | Retention does not authorize arbitrary execution. |
| New workflow-state module in clients | Rejected | Workflow ownership belongs to later orchestration. |
| Persistent cache or automatic refresh | Rejected | Session snapshot is the stated reuse scope. |
| Thread/process worker for copying | Not added | Short in-memory work; no measured blocking issue. |
| New exception class | Not added | Existing connection error carries a specific access stage. |

### Layer 3: Wiring

**Dependency direction:** workflow callers depend on `ToolGateway` and application contracts; `McpToolGateway` implements the Protocol and alone depends on MCP SDK types. Definition contracts stay in `clients/mcp_tools.py`; `clients/` never imports `services/`.

**Composition root:** `create_amenity_search(settings)` injects the result of `create_mcp_tool_gateway(settings)`; DeepSearch's existing shared wiring remains. Factories create no sessions and the later workflow retains one shared gateway per run.

| Operation group | I/O / dependency | Placement | Ordering | Shared state / worker |
| --- | --- | --- | --- | --- |
| Session startup | Independent connections/handshakes | Event loop, owner tasks | Concurrent | Separate owners; no worker. |
| Initial listings | Independent after startup | Async-native SDK on event loop | Concurrent, collect/settle both | Per-server return values; no shared writes. |
| Verify/group/publish | Needs both catalogs | Short inline CPU work | Sequential after listings | Publish once under lifecycle lock. |
| Getter/deep copy | Needs successful snapshot; no I/O | Synchronous on event loop | After open | Caller-owned return value; no worker. |
| Workflow state/catalog | Needs copied definitions | Later component's local work | Before tool turn | Derived copies; gateway state unchanged. |
| Typed operations | Existing calls, waits and retries | Async-native event loop | Existing per-call ordering | Existing shared semaphore/rate bucket. |
| Invalidate/close | Serialize after lifecycle writer | Event loop, owner tasks | Invalidate then concurrent owner stops | Same lifecycle lock; no worker. |

The event loop is the thread scheduling asynchronous work. Listing waits let other tasks run. Adaptation and copying remain inline because they perform local dictionary work; revisit only if an actual capture shows sustained blocking. No threads or processes are added, and SDK sessions never cross loops.

A synchronous getter has no await point, so lifecycle tasks on the same loop cannot interrupt its copy. Lock ownership spans only setup/teardown; ordinary tool calls do not take the lifecycle lock. Later callers must finish their tool work before closing the shared gateway.

### Layer 4: Backing

- **Owner tasks and httpx2:** preserve verified SDK context ownership and transport compatibility.
- **Local results then publication:** one listing result never becomes visible as a complete two-server snapshot.
- **Session reuse:** repeated reads use exactly the setup data; no schema-change race between tool turns.
- **Server roles:** configured display names may vary; application context policy uses stable role keys.
- **Copy ownership:** frozen outer records alone cannot protect nested dictionaries from mutations.
- **No new stage classes:** definitions extend setup/handoff, not the feature's responsibility decomposition.
- **Preserved iteration-5 corrections:** absent hosted batch tools stay absent from requirements; removed probes do not return.

## Open verification items

| ID | Item | Closure |
| --- | --- | --- |
| OV-1 / OV-3 | Old probe verification | Retired: no connection-time probe; real response regressions fail per call. |
| OV-2 | Missing Firecrawl key behavior | Confirm on a separately authorized live run; no current behavior change. |
| OV-4 / OV-10 | Map/scrape timing and pool values | Measure on existing sample when needed; keep current constants meanwhile. |
| OV-5 | Retained crawl job/status fields | Observe if crawl is enabled; not needed for raw definitions. |
| OV-6 | Parallel/Firecrawl concurrency samples | Existing opt-in V2a/V2b; no new live test requirement here. |
| OV-7 / OV-12 | Wrapped throttles and SSE resume | Keep existing classification/backoff; observe rather than redesign transport. |
| OV-8 / OV-13 | Account rate window and map budget | Existing 10/min setting retained; tune only from account/live evidence. |
| OV-9 / OV-11 | Batch concurrency and tool names | Retired with removed batch-job mechanism. |
| OV-14 | SDK listing pagination | Inspect installed SDK before build; consume all pages within initial setup if needed. |
| OV-15 | Definition-copy size | Record only if real large catalogs cause blocking; no speculative worker or cap. |

## Handoffs to later sub-components

| To | Contract |
| --- | --- |
| C3.1.3 | Accept grouped raw definitions; select server/tool by context; derive restricted copies. |
| C3.1.3 | Missing source/tool or unsupported schema transformation fails before the LLM call. |
| C3.1.4 | Existing valid-empty results and typed per-call failures remain unchanged. |
| C3.1.6 | Existing candidate caps, URL policy, evidence attribution and scrape fan-out use remain. |
| C3.1.7 | Open shared gateway, read getter once, store grouped copy before discovery. |
| C3.1.7 | Finish tool work before close; discard state copy at run end or replace for a new session. |
| C3.1.6/C3.1.7 | Bind run/amenity log context above the gateway; do not pass identity into schema retrieval. |

**Build completion criteria:** #5 exposes complete server-grouped definitions through the Protocol, all access/lifecycle contracts above are verified offline, #10 no longer re-lists for diagnostics, #11 documents the grouped C3.1.3 contract, and #13 matches the implemented behavior. This document update performs none of those source changes.

---

# Appendix: C3.1.1 Iteration Report (Iteration 6: raw tool definitions)

## 1. Confirmation

Inputs read: the C3.1.1 spec in `deep_search_context.md`, the existing C3.1.1 implementation plan, and the new requirements attached in the user's message, including the subsequent decisions in this chat. The attachment supersedes the flat tool-name dictionary originally proposed for C3.1.3.

"Implemented" means the current spec plus the plan's iteration-5 corrections, corroborated by the local gateway and sample runner. The plan's older iteration-4 batch resolver and connection-time probe are historical, not the current baseline. No live servers were contacted. This report describes changes, not completed implementation.

Result: **2 ADD, 2 MODIFY, 0 REMOVE, 0 DECISION-GATED**. Report IDs are local to this iteration; the plan maps A1 to A8, A2 to A9, M1 to M14, and M2 to M15.

Artifact paths below are relative to the repository root. #n refers to the original plan's file-todo number, retained in the updated plan. New symbols absent from that plan are marked (illustrative). Inferred supporting changes are explicitly marked.

## 2. Current traceflow with change locations

```text
McpToolGateway
├─ open
│  ├─ _start_sessions
│  ├─ verify_capabilities
│  │  ├─ _list_tools per server                        ◄── M1, A2
│  │  │  └─ retain only names and argument-name sets   ◄── M1
│  │  └─ require web_search, map and scrape
│  └─ on failure or cancellation: aclose               ◄── M2
├─ definition-reading capability absent                ◄── A1
├─ typed search, map, scrape, fan-out and crawl
└─ aclose: stop both owner tasks                       ◄── M2
```

| ID | Class | Summary |
| --- | --- | --- |
| A1 | ADD | Synchronous definition accessor returning a deep copy |
| A2 | ADD | Server-grouped exposure and workflow/catalog handoff contract |
| M1 | MODIFY | Preserve all full definitions from existing listing responses |
| M2 | MODIFY | Publish and invalidate a complete session-scoped snapshot |

## 3. ADD points

### A1: Definition accessor with nested-copy isolation

| Artifact | Change |
| --- | --- |
| `backend/src/clients/mcp_tools.py` (#5), `ToolGateway`, `McpToolGateway` | add: `get_tool_definitions` (illustrative) exposes stored application-owned definitions without network requests; each result is independent through nested schema objects. |
| `backend/tests/services/deep_search/test_mcp_tool_gateway.py` (#9) | add: assertions for repeated local reads and mutation isolation between returned definitions and retained data. |
| `backend/src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py` (#12) | add: equivalent accessor contract coverage for the component harness. |
| `backend/src/services/deep_search/feature_sample_runs/mcp_tool_gateway_sample_run.py` (#10), `_stage_open` (illustrative symbol) | modify: replace the runner's extra post-open listing requests with the public accessor (inferred supporting change). |
| `backend/src/services/deep_search/feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (#13) | modify: document the local-read and nested-copy isolation acceptance criteria. |

BEFORE
```text
Workflow caller
├─ await gateway.open
└─ no public definition-reading interface
```

AFTER
```text
Workflow caller
├─ await gateway.open
└─ get_tool_definitions                              ◄── NEW
   ├─ read the stored snapshot without network I/O   ◄── NEW
   └─ return independent nested schema objects       ◄── NEW
      └─ caller edits leave gateway data unchanged   ◄── NEW
```

Behaviour change: callers can obtain full definitions without another listing request or access to private SDK sessions.

### A2: Keep server identity in the exposed definitions

| Artifact | Change |
| --- | --- |
| `backend/src/clients/mcp_tools.py` (#5), `ToolGateway`, `McpToolGateway` | add: expose nested dictionaries keyed first by stable application server identity and then by MCP tool name. |
| `backend/src/services/deep_search/feature_context/deep_search_context.md` (#11), C3.1.1 and C3.1.3 | modify: document grouped workflow state and replace the catalog builder's flat input contract; context policies select server and tool. |
| `backend/tests/services/deep_search/test_mcp_tool_gateway.py` (#9) and `backend/src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py` (#12) | add: definitions with the same tool name on different servers remain distinct. |
| `backend/src/services/deep_search/feature_sample_runs/mcp_tool_gateway_sample_run.py` (#10) | modify: display definitions grouped by server and demonstrate the workflow-state handoff without invoking later components. |
| `backend/src/services/deep_search/feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (#13) | modify: capture grouping and source-selection acceptance criteria. |
| `backend/src/services/deep_search/amenity_search.py` (#6) | check only: retain gateway injection; workflow-state population is a later orchestration handoff, not a new C3.1.1 stage. |

BEFORE
```text
Gateway capability check
├─ Parallel listing used separately
├─ Firecrawl listing used separately
└─ C3.1.3 proposes a flat raw-definition input
```

AFTER
```text
Gateway definition handoff                             ◄── NEW
├─ parallel: definitions keyed by tool name            ◄── NEW
├─ firecrawl: definitions keyed by tool name           ◄── NEW
│  └─ same names across servers remain separate        ◄── NEW
└─ workflow state receives the grouped definitions     ◄── NEW
   └─ C3.1.3 context selects source server and tool    ◄── CHANGED
      └─ missing selection: explicit catalog failure   ◄── NEW
```

Behaviour change: callers retain source identity without cross-server overwrites or implicit server fallback.

## 4. MODIFY points

### M1: Preserve full definitions from the existing listing boundary

| Artifact | Change |
| --- | --- |
| `backend/src/clients/mcp_tools.py` (#5), `_list_tools`, `verify_capabilities`, `_require` | modify: preserve names, nullable descriptions and complete input schemas for every listed tool; capability checks still inspect only the existing required tools and arguments. |
| `backend/src/clients/mcp_tools.py` (#5), `RawToolDefinition` (illustrative) | add: an application-owned definition contract so SDK tool objects do not cross the gateway boundary. |
| `backend/src/clients/mcp_tools.py` (#5), `mcp.tools_listed` | modify: keep the existing per-server boundary summary useful with full definitions; no full schema payload dump is required (inferred). |
| `backend/tests/services/deep_search/test_mcp_tool_gateway.py` (#9) and `backend/src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py` (#12) | modify: fixtures include unused tools, optional descriptions, nested constraints and referenced definitions so schema preservation is observable. |
| `backend/src/services/deep_search/feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (#13) | modify: record full-schema fidelity and unchanged required-capability checks. |
| `backend/src/services/deep_search/feature_context/deep_search_context.md` (#11) | modify: distinguish retaining all definitions from exposing a context-limited LLM catalog. |

BEFORE
```text
verify_capabilities
├─ _list_tools on each server
│  ├─ read SDK tool definitions
│  └─ reduce each schema to top-level argument names
└─ _require validates expected tool and argument names
```

AFTER
```text
verify_capabilities
├─ _list_tools on each server
│  ├─ retain every listed tool definition                ◄── CHANGED
│  ├─ retain nullable description and complete schema    ◄── NEW
│  └─ preserve nested constraints and references         ◄── NEW
└─ _require reads argument names from retained schemas   ◄── CHANGED
   └─ expected names and required arguments unchanged
```

Behaviour change: information previously discarded is available for C3.1.3 without broadening the required capability set.

### M2: Snapshot availability follows the successful gateway session

| Artifact | Change |
| --- | --- |
| `backend/src/clients/mcp_tools.py` (#5), `__init__`, `open`, `verify_capabilities`, `aclose` | modify: retain one complete snapshot per successfully opened gateway session; partial setup never becomes readable, and failed opening or closing invalidates it. |
| `backend/src/clients/mcp_tools.py` (#5), `get_tool_definitions` (illustrative) | add: reject reads before successful opening, during unavailable lifecycle states and after closing with a clear lifecycle error. |
| `backend/src/exceptions/mcp.py` (#4), `McpConnectionError` | modify: document definition-access lifecycle failures using the existing error family; the exact stage is a plan choice. |
| `backend/tests/services/deep_search/test_mcp_tool_gateway.py` (#9) and `backend/src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py` (#12) | add: unsuccessful/cancelled opening, closed access, and session reuse do not leak partial or stale definitions. |
| `backend/src/services/deep_search/feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (#13) | modify: include snapshot lifetime and failed-open cleanup criteria. |
| `backend/src/services/deep_search/feature_sample_runs/mcp_tool_gateway_sample_run.py` (#10) | modify: retain opening and closing error reporting while demonstrating valid post-open access. |

BEFORE
```text
McpToolGateway
├─ open
│  ├─ start both sessions
│  ├─ verify required capabilities
│  └─ any failure: close both sessions and propagate
└─ aclose: stop both sessions
```

AFTER
```text
McpToolGateway
├─ open
│  ├─ begin with definitions unavailable                ◄── NEW
│  ├─ start both sessions
│  ├─ obtain and verify the complete definition set     ◄── CHANGED
│  ├─ success: publish one session snapshot             ◄── NEW
│  └─ failure: invalidate, close and propagate          ◄── CHANGED
├─ definition access outside successful open: error     ◄── NEW
└─ aclose: invalidate snapshot and stop both sessions   ◄── CHANGED
```

Behaviour change: callers receive a consistent successful-session snapshot or an explicit lifecycle failure, never partial setup data.

## 5. REMOVE points

None. Typed execution operations, transport behavior and previous iteration-5 corrections remain.

## 6. DECISION-GATED points

None. Approach A and server grouping are explicitly finalized by the user. No confirmed build-time correction is reversed.

## 7. Unchanged

- `open` returns no definitions; factories open no sessions.
- One owner task per server and no SDK objects above the gateway.
- Required capabilities: Parallel search and Firecrawl map/scrape with existing arguments.
- Crawl/status remain optional; no batch resolution or connection-time shape probe.
- Typed operation outputs, URL injection rules, scrape fan-out and per-URL degradation.
- Existing timeouts, transport library, retry classification/backoffs and Firecrawl pacing.
- No generic execution of every listed tool and no new LLM calls.
- Workflow and catalog construction remain later-component responsibilities.

## 8. Component traceflow after all points

```text
Workflow caller
├─ await gateway.open
│  ├─ _start_sessions
│  ├─ verify_capabilities
│  │  ├─ _list_tools per server                           ◄── M1
│  │  │  └─ full application-owned raw definitions        ◄── M1
│  │  ├─ keep separate server groups                      ◄── A2
│  │  └─ require existing tools and arguments
│  ├─ success: publish one validated session snapshot     ◄── M2
│  └─ failure: invalidate, close and propagate            ◄── M2
├─ get_tool_definitions: local deep copy                  ◄── A1
│  └─ grouped definitions stored in workflow state        ◄── A2
│     └─ C3.1.3 selects server/tool and derives catalog   ◄── A2
├─ existing typed execution after guard admission
└─ await gateway.aclose
   └─ invalidate snapshot and stop both owner tasks       ◄── M2
```

The workflow-state write and catalog-builder call above are integration contracts for later components, not implemented stages of C3.1.1.

## 9. Flags

| ID | Finding and disposition |
| --- | --- |
| F1 | The plan mixes iteration-3/4 history with iteration-5 behavior. Iteration 6 uses the current spec/code baseline; obsolete batch and probe decisions must not be rebuilt. |
| F2 | C3.1.3 still declares a flat dictionary and has stale crawl-based overview text. Update its raw-definition contract and server-selection policy; leave unrelated evidence-workflow redesign outside this iteration. |
| F3 | The gateway has no implemented workflow-state owner. Population of `raw_tool_definitions` is a C3.1.7 handoff; the gateway must not import workflow schemas or invent a new orchestrator. |
| F4 | `_stage_open` currently performs extra `tools/list` requests after opening. Replace those diagnostic reads with the accessor so the sample respects snapshot reuse. |
| F5 | A clear lifecycle error is required, but the attachment names no class/stage. The implementation plan must choose these explicitly from the existing error family. |
| F6 | The attachment does not define same-session explicit re-verification behavior. Preserve the one-snapshot requirement; the plan must prevent re-listing through this public helper. |
| F7 | Pagination handling of `Client.list_tools` is not established by the old plan. At build time confirm whether the SDK aggregates pages; if it exposes a continuation, consume it within the same initial listing pass. Do not claim one wire request per server without that check. |
| F8 | Excluding the Testability bullet from critical decisions does not remove the existing plan's verification section. Keep proportionate offline contract checks; do not execute live searches or scrapes for this documentation task. |


## Iteration 6 implementation record

- Added frozen `RawToolDefinition`, grouped `RawToolDefinitions`, and synchronous deep-copy access
  through `ToolGateway`. Full definitions are copied at the SDK boundary and on each public read.
- SDK 2.2.0 `Client.list_tools` returns one page with `next_cursor`; the gateway follows `cursor`
  using cache bypass until the complete initial listing has been collected.
- Lifecycle locking serializes setup, explicit verification and close. Successful open publishes
  once; failed/cancelled setup settles listing tasks before owner cleanup. Closing invalidates
  before shutdown. Session-owner synchronization resets when starting a later session.
- Boundary summaries and state transitions share a per-open opaque ID. The existing runner reads
  the public snapshot and demonstrates grouped workflow-state handoff in both opening paths.
- Updated exception documentation, C3.1.1/C3.1.3 contracts and the component test plan. No later
  workflow orchestrator, catalog builder, LLM turn or generic executor was added.
- Added seven contract cases in each existing gateway suite, including paginated source fidelity,
  mutation isolation, grouping, reuse, setup errors, cancellation, queued close and reopening.


### Verification completed

- Both existing gateway suites: **148 passed in 111.90 s**.
- Focused iteration-6 cases across both suites: **14 passed, 134 deselected**.
- Syntax parsing passed for all five changed Python files; `git diff --check` passed.
- Tests ran outside the sandbox because Windows asyncio socket-pair initialization blocks inside
  it. No hosted MCP services or live billed search/scrape operations were invoked.
