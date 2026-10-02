# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl)

**Scope.** The prompt says "mechanism 1 component M1.3", but the item list and selection (context lines 2794-2835) point to **Mechanism 3, C3.1.1**. That is what is planned. C3.1.2 onward (tool-schema building, phase gating, clamps, crawl cache, URL resolution, C3.2) is out of scope. Locked C3.1.1 decisions are not reopened.

**Checked against the real SDK** (`mcp==2.2.0`, downloaded and read):
- `Client(transport)` and `streamable_http_client(...)` are one-shot. The gateway never reconnects or replaces a `Client`: a timeout is our side giving up on waiting, so the open session stays in use.
- `Client` holds an anyio task group, so it must be exited in the task that entered it.
- The caller-owned HTTP client is `httpx2.AsyncClient` (`httpx2==2.12.0` is already pinned).
- `CallToolResult` has `content`, `structured_content`, `is_error`. `Client` caches `tools/list` by default, so the capability check uses `cache_mode="bypass"`.
- Endpoints: Parallel `https://search.parallel.ai/mcp` (bearer; anonymous works at a lower limit). Firecrawl `https://mcp.firecrawl.dev/v2/mcp` (bearer).
- `mcp.server.MCPServer` serves in-process, so tests need no network.

## 0. Cross-mechanism check (updates to earlier mechanisms)

| Earlier piece | Finding | Action in this plan |
| --- | --- | --- |
| `AmenitySearch.__init__` (M1.1/M1.2) | Takes only Places and Routes clients | Add required keyword-only `tool_gateway`; `aclose()` also closes it |
| `create_amenity_search` (M1 composition root) | Builds only Google clients | Also build the gateway (no I/O, no session opened) |
| Direct `AmenitySearch(...)` call sites | Would break on the new parameter | Update `test_place_discovery.py`, `test_accessibility_enrichment.py`, `test_result_attachment.py`, `result_attachment_sample_run.py` |
| `Settings` | No server keys or URLs | Add optional keys and URLs; existing runs and tests keep working |
| `deep_search_context.md` | "Current code" line says `__init__` takes only Places and Routes clients; SDK notes missing | One cross-mechanism note; locked C3.1.1 text untouched |
| M1.3 rename to `PredefinedMetricsRecord` / `AmenityMetricsSet` | Not needed by the gateway | Not done here; belongs to C3.2.5 |
| M6 tool names (`parallel_web_search`, `firecrawl`) vs MCP names (`web_search`, `firecrawl_crawl`) | Gateway exposes typed ops, not tool names | Mapping is C3.1.2's job; RC10 is a separate upstream M6 change |

---

## 1. File and Module Structure (Build todos)

No prompt module: there is no LLM call. The gateway is infrastructure, so it lives in `clients/`, not as a mechanism class.

| # | File | New/Modify | Purpose and ownership |
| --- | --- | --- | --- |
| 1 | `backend/requirements.txt` | Modify | Add `mcp==2.2.0`, `mcp-types==2.2.0` and transitive pins |
| 2 | `backend/src/core/config.py` | Modify | Add `parallel_api_key`, `firecrawl_api_key` (`str \| None`) and the two server URLs with defaults |
| 3 | `backend/.env.example` | Modify | Document `PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, optional URLs |
| 4 | `backend/src/exceptions/mcp.py` | New | `McpGatewayError` tree, each with `stage` |
| 5 | `backend/src/clients/mcp_tools.py` | New | Result contracts, `ToolGateway` Protocol, `McpToolGateway`, private `_ServerSession`, parsers, `create_mcp_tool_gateway` |
| 6 | `backend/src/services/deep_search/amenity_search.py` | Modify | Inject `tool_gateway`, close it in `aclose`, build it in `create_amenity_search` |
| 7 | `test_place_discovery.py`, `test_accessibility_enrichment.py`, `test_result_attachment.py` | Modify | Pass `tool_gateway` at existing construction helpers |
| 8 | `feature_sample_runs/result_attachment_sample_run.py` | Modify | Pass `tool_gateway=None` |
| 9 | `backend/tests/services/deep_search/test_mcp_tool_gateway.py` | New | Offline fixtures against an in-process fake MCP server |
| 10 | `backend/src/services/deep_search/feature_sample_runs/mcp_tool_gateway_sample_run.py` | New | Live runner (section 4.1) |
| 11 | `backend/src/services/deep_search/feature_context/deep_search_context.md` | Modify | One cross-mechanism note |

Result contracts live in `clients/mcp_tools.py`, not `schemas.py`, because `clients/` must not import `services/`.

---

## A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: (orchestrator, later) sequences the responsibilities
   └─ Responsibility 2: AmenitySearch: find amenities and collect their facts
      └─ Mechanism 3 Workflow: run_llm_metric_resolution (later sub-components)
         └─ Component C3.1: evidence acquisition loop (later)
            └─ Sub-component C3.1.1 (this plan): MCP tool gateway, a client-boundary capability
               ├─ Stage 1: open, start both server sessions, one owner task each
               ├─ Stage 2: verify_capabilities, check tool and argument names at connect
               ├─ Stage 3: search_web, typed web_search on Parallel
               ├─ Stage 4: crawl_site, typed firecrawl_crawl on Firecrawl (starts a job, returns its id)
               ├─ Stage 5: read crawl job by id, poll or re-read firecrawl_check_crawl_status on the same Client after a timeout (internal)
               └─ Stage 6: aclose, close every session in its owner task
```

C3.1.1 adds no workflow method to `AmenitySearch`. `run_llm_metric_resolution` will call `open` first and `aclose` last when built later.

## B. Data Contracts

| Contract | Purpose | Fields | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `McpServerConfig` | one server's connection settings | `name: str` · `url: str` · `api_key: str \| None` · `call_timeout_seconds: float` | immutable | factory → gateway |
| `SearchExcerpt` | one search hit | `url: str \| None` · `title: str \| None` · `text: str` | immutable | Stage 3 → C3.1.2 |
| `WebSearchResult` | typed search outcome | `objective: str` · `search_queries: tuple[str, ...]` · `excerpts: tuple[SearchExcerpt, ...]` · `retrieved_at: str` | immutable | Stage 3 → C3.1.2 |
| `CrawledPage` | one crawled page | `url: str` · `title: str \| None` · `text: str` | immutable | Stage 4 → C3.1.2 |
| `CrawlResult` | typed crawl outcome | `url: str` · `job_id: str \| None` · `pages: tuple[CrawledPage, ...]` · `retrieved_at: str` | immutable | Stage 4 → C3.1.2 |
| `ToolFailure` | typed per-call failure, returned not raised | `tool: str` · `kind: tool_error \| timeout \| rate_limited \| transport \| unparseable` · `message: str` | immutable | Stages 3, 4 → C3.1.2 |
| `McpGatewayError` tree | gateway-level failure, raised | `McpConnectionError` (only at open) · `McpToolUnavailableError`; each has `stage` | immutable | Stages 1, 2 → run |

> Rules: an empty hit list is a valid `WebSearchResult` with `excerpts=()`, not a failure. `retrieved_at` is stamped once per result on receipt. Keys appear only in `McpServerConfig.api_key`, never in messages, logs or exceptions.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `ToolGateway` | Protocol | `open()` · `search_web(objective, search_queries)` · `crawl_site(url, limit, depth)` · `aclose()` | `McpToolGateway` (real), test fake | `AmenitySearch` |
| `ClientFactory` | callable alias | `(McpServerConfig) -> async context manager yielding mcp.Client` | Streamable HTTP (default), in-process fake (tests) | `_ServerSession` |
| `mcp.Client` | external SDK | `list_tools(cache_mode)` · `call_tool(name, arguments, read_timeout_seconds)` | SDK | `_ServerSession`, `McpToolGateway` |
| `httpx2.AsyncClient` | external SDK | carries the `Authorization` header | SDK | default `ClientFactory` |
| `Settings` | existing config | keys and URLs | one | `create_mcp_tool_gateway` |

## D. Class & Method Blueprint

**`McpToolGateway`** implements `ToolGateway`; owns sessions, per-server semaphores, retry, timeouts, parsing.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | `(parallel: McpServerConfig, firecrawl: McpServerConfig, *, search_concurrency: int, crawl_concurrency: int, client_factory: ClientFactory)` | hold configs, semaphores, connect seam |
| `open` | `() -> None [raises: McpConnectionError, McpToolUnavailableError]` | start both sessions together, then check capabilities |
| `verify_capabilities` | `() -> None [raises: McpToolUnavailableError, McpConnectionError]` | list tools on both servers, match required names |
| `search_web` | `(objective: str, search_queries: Sequence[str]) -> WebSearchResult \| ToolFailure [raises: McpConnectionError]` | run `web_search` with retry, parse excerpts |
| `crawl_site` | `(url: str, limit: int, depth: int) -> CrawlResult \| ToolFailure [raises: McpConnectionError]` | start `firecrawl_crawl`, read the job by id; accept final pages if returned |
| `aclose` | `() -> None` | idempotent; end every owner task |
| `_call_with_retry` | `(session, tool: str, arguments: dict, *, retry_kinds) -> CallToolResult \| ToolFailure` | one bounded call with transient retry |
| `_read_crawl_job` | `(session, job_id: str) -> CrawlResult \| ToolFailure` | poll or re-read the job by id; never start the crawl again |

**`_ServerSession`** (private) owns one server's Client lifetime.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `start` | `() -> None [raises: McpConnectionError]` | launch the owner task, wait until the Client is ready |
| `client` | `-> Client` | the one open Client, shared by all calls to that server |
| `stop` | `() -> None` | release the owner task and await it |

**Module-level pure functions** (no state, tested from fixtures):

| Function | Signature | Purpose (one line) |
| --- | --- | --- |
| `_parse_search_result` | `(result: CallToolResult, objective, queries, retrieved_at) -> WebSearchResult` | content blocks to typed excerpts |
| `_parse_crawl_result` | `(result: CallToolResult, url, retrieved_at) -> CrawlResult \| job id` | final pages, or a job id to poll |
| `_classify_failure` | `(error_or_result) -> ToolFailure kind` | map exception type or `is_error` text to a failure kind |
| `create_mcp_tool_gateway` | `(settings: Settings) -> McpToolGateway` | composition root for the gateway; opens nothing |

**`AmenitySearch`** (existing) changes:

| Change | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` | adds keyword-only `tool_gateway: ToolGateway` | the locked injected test seam |
| `aclose` | `() -> None` | also awaits `tool_gateway.aclose()` |
| `create_amenity_search` | `(settings) -> AmenitySearch` | also builds the gateway |

## E. Runtime Flow: Data Object Journey

Request path (runner and fixtures excluded):

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `open` → `_ServerSession.start` ×2 | two `McpServerConfig` | one owner task and one `Client` per server | both sessions ready |
| 2 | `verify_capabilities` | `tools/list` from each server | pass or `McpToolUnavailableError` | catalogs checked |
| 3 | `search_web` | objective, queries | `WebSearchResult` or `ToolFailure` | typed excerpts |
| 4 | `crawl_site` | url, limit, depth | starts a crawl job, returns `CrawlResult` or `ToolFailure` | typed pages |
| 5 | `_read_crawl_job` | job id | `firecrawl_check_crawl_status` on the same `Client`; the job lives on Firecrawl's side, so the id is valid for any later request | pages or `ToolFailure` |
| 6 | `aclose` | all sessions | tasks ended, clients closed | gateway closed |

**Transformation trace (shape only):**
```
(objective, search_queries)
 → arguments{ objective, search_queries[] }
 → [search slot] → shared Client → call_tool("web_search") under timeout
 → CallToolResult{ content[], structured_content?, is_error }
 → is_error or exception → ToolFailure{ tool, kind, message }     # transient kinds retry first
 | parsed → WebSearchResult{ objective, search_queries, excerpts[], retrieved_at }

(url, limit, depth)
 → arguments{ url, limit, maxDiscoveryDepth, allowExternalLinks=false }
 → [crawl slot] → shared Client → call_tool("firecrawl_crawl") under timeout   # returns quickly with a job id
 → CallToolResult
 → job id      → poll firecrawl_check_crawl_status(job id) until complete → CrawlResult{ url, job_id, pages[], retrieved_at }
 | final pages → CrawlResult{ url, job_id?, pages[], retrieved_at }          # accepted if the server returns them
 | a status read times out → ask again with the same job id (bounded by the crawl deadline) → CrawlResult | ToolFailure(timeout)
 | start call times out before any id → ToolFailure(timeout), crawl not re-issued
 | is_error / exception → ToolFailure
```

**Approach at the real decision points:**
- Search retries on timeout, transport error and rate limit (waits 2 s then 3 s). A non-rate-limit `is_error` does not retry. Exhaustion returns a `ToolFailure`.
- Crawl start retries only on rate limit. It is never re-issued after a timeout or transport error (the job may already exist and be billed). Status reads are safe to repeat: after a timeout, the same read is sent again with the same job id on the same `Client`, until the crawl deadline.
- Only "cannot connect" and "expected tool or argument missing" raise. Everything else degrades per item (D5).
- The gateway never replaces a session or `Client`. A timeout means our side stopped waiting; the session stays open and serves the next call. If the session were actually dead, calls would keep returning `ToolFailure(transport)`, and V2a and V2b would show it.

## F. Method Detail

**`_ServerSession` (one owner task per server)**
- The owner task builds the `httpx2` client and `Client` through the factory, publishes the `Client`, waits for a release signal, then exits both contexts in the same task.
- All calls to that server share the one `Client`.
- **Failure:** start failure re-raises as `McpConnectionError(stage="open")`. There is no replace step.

**`open` and `verify_capabilities`**
- Start both sessions together; if one fails, stop the other and raise. Then `list_tools` with cache bypass on both, together.
- Required: Parallel `web_search` with `objective`, `search_queries`; Firecrawl `firecrawl_crawl` with `url`, `limit`, `maxDiscoveryDepth`, `allowExternalLinks`; Firecrawl `firecrawl_check_crawl_status` with its job id argument (exact name fixed from `tools/list` and the live capture). The status tool is required because every crawl result is read through it.
- A miss raises `McpToolUnavailableError(stage="verify_capabilities")`; a keyless Firecrawl lacks the crawl tool, so this also detects a missing key.
- With no Parallel key the header is omitted and one `mcp.session_opened` log says `authenticated=false`.

**`_call_with_retry`**
- Take the server semaphore slot, use the shared client, wrap `call_tool` in both `asyncio.timeout` and the SDK `read_timeout_seconds`, map the outcome with `_classify_failure`, and sleep through backoffs on transient kinds. A repeat attempt reuses the same `Client`.
- Rate-limit detection: exception type or HTTP 429; for `is_error`, text match. Final signal is fixed from the live capture.

**`crawl_site`**
- Validate `limit >= 1`, `depth >= 0`, `http(s)` URL (raise `ValueError`). Send `allowExternalLinks=false`.
- The start call returns quickly with a job id (the crawl runs on Firecrawl's side). Poll `firecrawl_check_crawl_status` with that id every 3 s inside the overall crawl deadline, then return the pages Firecrawl holds for that id.
- If a poll times out, send the same status request again with the same id on the same `Client`. The id belongs to the job, not to the session.
- Pages in the first response: return them (accepted if the server returns them).
- Timeout of the start call before any id arrives: `ToolFailure(timeout)`, no re-issue. Deadline reached while polling: `ToolFailure(timeout)` carrying the job id in the message, so the job is not lost.
- Page and depth clamps and host restriction belong to C3.1.x.

**Parsers**
- Prefer `structured_content`, then JSON-decode text blocks, then a single unstructured excerpt.
- Shapes are provisional (from docs) and fixed after one real capture per server. An unrecognised shape returns `ToolFailure(unparseable)`. Parsing runs inline.

---

## 4. Sample Runner and Fixture Set

### 4.1 Live sample runner (required)

`feature_sample_runs/mcp_tool_gateway_sample_run.py`: manual, stage-by-stage, real servers, no LLM (so no prompt module and no worked-pair examples).

**How to run** from `backend/` (needs `PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, network):
- `python -m src.services.deep_search.feature_sample_runs.mcp_tool_gateway_sample_run`
- Flags: `--v2a`, `--v2b`, `--crawl-url <url>`.

**What it seeds:** loads `data/m1_1_discovered_places.json` (the real M1.1 capture the M1.2 runner uses) and reads the first place's `display_name.text` and `website_uri` from the dict. M1.1, M1.2, M1.3 are not called. Objective and queries are hand-written, not copied from any prompt. Crawl uses `limit=3`, `depth=1`.

**What it prints:** one titled section per stage.

| Section | Content |
| --- | --- |
| INPUT STATE | seeded amenity, objective, queries, crawl arguments |
| STAGE 1, open and capability check | per server: connected, tool count, required tools and args found, status tool present, key present yes/no |
| STAGE 2, `search_web` | request, excerpt count, first URLs, lengths, `retrieved_at`, or `ToolFailure` |
| STAGE 3, `crawl_site` | request, page count, URLs, `job_id`, lengths, or `ToolFailure` |
| STAGE 4, `aclose` | owner tasks ended, second `aclose` is a no-op |

Raw `CallToolResult` bodies and per-attempt records are read from the `homescout.deep_search` logger via a collecting handler. On `McpGatewayError`: print class, `stage`, message, exit non-zero. A returned `ToolFailure` is printed and gives non-zero exit at the end. Nothing is written to disk.

**Opt-in verification stages** (these spend credits):

| Flag | What it checks |
| --- | --- |
| `--v2a` | ten concurrent `search_web` calls checked against their own requests; one extra call cancelled mid-flight, others finish, follow-up works |
| `--v2b` | two concurrent `crawl_site` calls on different small URLs do not interfere; `verify_capabilities` fired during a crawl (fast call on the same Firecrawl Client); one crawl wait cut short by a forced timeout, then other in-flight calls and a follow-up call confirm the same session is still usable, and the cut-short crawl is read again with its job id on the same `Client` |

### 4.2 Offline fixture set

`tests/services/deep_search/test_mcp_tool_gateway.py`: pytest with in-process `MCPServer` injected via the client factory. No network, no keys. Asserts:

| Area | Assertion |
| --- | --- |
| Capabilities | missing tool, missing argument, or keyless Firecrawl without the crawl tool raises `McpToolUnavailableError` with `stage="verify_capabilities"`; a full set passes |
| Typed results | `retrieved_at` set; `is_error` returns `ToolFailure` (not raised); empty body gives zero excerpts |
| Crawl shapes | both shapes parse, including job-id polling to completion; a missing `firecrawl_check_crawl_status` tool raises `McpToolUnavailableError` |
| Retry | search retries twice with sleeps 2.0 then 3.0, then `ToolFailure`; non-transient `is_error` makes one attempt |
| Crawl timeout | a timed-out status read is sent again with the same job id on the same `Client`; a second `firecrawl_crawl` is never sent |
| Arguments | crawl sends `maxDiscoveryDepth` and `allowExternalLinks=false`; bad arguments raise `ValueError` |
| Concurrency | in-flight calls never exceed semaphore size; ten concurrent searches return their own results |
| Session scope | call before `open` raises; `aclose` idempotent; failed `open` leaves no running task |
| Forced timeout | other in-flight calls finish and the same `Client` serves the next call (no new `Client` is built) |
| Secrets | keys never appear in log records or exception text |

---

# Architecture and Modularity Decisions

## Layer 1: Glance

**A. Architecture at a Glance**
- **Shape:** one concrete gateway behind one narrow Protocol, injected into `AmenitySearch`. Each server session lives in its own task.
- **Seams (where things can change independently):**
  - Gateway contract: `ToolGateway`, so `AmenitySearch` and tests see no MCP types.
  - Connect step: client factory (Streamable HTTP in production, in-process in tests).
  - Server settings: URLs and keys from `Settings`.
- **Component list:** `ToolGateway`, `McpToolGateway`, `_ServerSession`, result dataclasses and `ToolFailure`, `McpGatewayError` tree.

## Layer 2: Justification

**B. Component Map**

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `ToolGateway` | contract for the two typed operations | result types | Yes: tests need no network |
| `McpToolGateway` | retry, timeout, semaphores, parsing, capability check | `_ServerSession`, `ClientFactory` | implements |
| `_ServerSession` | one Client lifetime per server | `ClientFactory`, `mcp.Client` | none (concrete, private) |
| `McpServerConfig`, result types, `ToolFailure` | typed settings and outputs | none | none (frozen dataclasses) |
| `McpGatewayError` tree | connect and missing-tool exits with `stage` | none | none (exception tree) |

**C. Decisions & Justifications**

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| `ToolGateway` Protocol | locked test seam; service must not see MCP types | C3.1.2 tests need live servers; SDK types leak |
| One owner task per server | Client must exit in the task that entered it | `aclose` from another task raises a scope error |
| Crawl job id read via `firecrawl_check_crawl_status` | job lives on Firecrawl's side; a timed-out wait is recovered by asking again | a timeout loses the crawl or starts a second billed one |
| `ClientFactory` kwarg | tests must not call the network | gateway tests need monkeypatching or live servers |
| `ToolFailure` returned, not raised | D5: one failed call must not abort the gather | one failed search aborts every concurrent pipeline |
| Two per-server semaphores | locked per-server limits | a slow crawl starves searches |
| `McpServerConfig` dataclass | two servers share one config shape | two parallel sets of positional arguments |
| Typed results in `clients/mcp_tools.py` | `clients/` must not import `services/` | callers parse raw content blocks |
| Optional keys, header omitted when `None` | existing runs and tests have no server keys | every existing test and runner fails on settings load |

**D. Kept Concrete / Rejected**

| Considered | Decision | Reason |
| --- | --- | --- |
| Gateway class per server | rejected | logic is identical |
| Generic "call any MCP tool" gateway | rejected | only two tools are needed |
| Exposing `Client` or `ClientSession` to callers | rejected | leaks SDK types and ownership |
| Per-call sessions | rejected | locked once-per-run sessions |
| `AsyncExitStack` in the caller's task | rejected | `aclose` may run in a different task than `open` |
| Replacing the session or `Client` after a failure (generations, leases, reconnect) | rejected | over-engineering: a timeout means our side stopped listening, the session is still valid, and a lost crawl wait is recovered by job id on the same `Client` |
| Retry library | not added | two fixed backoffs |
| Parallel `session_id` | not added | ignored on paid keys |
| `web_fetch` on Parallel | not added | locked unused |
| Crawl re-issue on timeout or transport error | rejected | would create a second billed job; the status read by job id is repeated instead |
| Thread or process offload for parsing | not added | small inline JSON |
| Result types in `schemas.py` | rejected | layering |
| Protocol for `_ServerSession` | kept concrete | one implementation |
| `AmenitySearch` workflow method for C3.1.1 | not added | no mechanism stage belongs here yet |

## Layer 3: Wiring

**E. Dependency Direction**
```
AmenitySearch → [ToolGateway] ← McpToolGateway → _ServerSession → mcp.Client → httpx2.AsyncClient
McpToolGateway → McpServerConfig, result types, McpGatewayError
create_amenity_search → create_mcp_tool_gateway → Settings
```

**F. Composition Root**
- **Where:** `create_amenity_search(settings)` in `amenity_search.py`, which calls `create_mcp_tool_gateway(settings)` in `clients/mcp_tools.py`.
- **Selects:** keys and URLs from `Settings`; module-constant starting values (unmeasured, configurable): search timeout 30 s, crawl overall deadline 180 s (each start or status call uses its server's per-call timeout), retry waits 2 s then 3 s, crawl poll 3 s, search semaphore 4, crawl semaphore 2.
- **Lifecycle:** the factory opens nothing. `open()` runs at the start of `run_llm_metric_resolution` and `aclose()` at its end. `AmenitySearch.aclose()` also closes the gateway (covers a leaked session).

**G. Async Execution Map** (placement set by blocking behavior, ordering by data dependency, decided separately)

| Operation group | Operations and I/O | Data dependency | Placement | Ordering | Shared-state handling | Blocking / worker |
| --- | --- | --- | --- | --- | --- | --- |
| Session open | HTTP connect, MCP handshake per server | independent | event loop, one owner task per server | concurrent (gather of the two ready signals) | each owner task writes only its own session | none; no worker |
| Capability check | `list_tools` per server | independent; needs open sessions | event loop | concurrent (gather) | read only | none; no worker |
| Search call path | semaphore wait, `call_tool`, backoff sleep | retry depends on previous attempt | event loop | sequential inside one call; calls from different amenities are gathered by the caller (later) | per-server semaphore bounds in-flight; results returned, no shared writes | none; every call under `asyncio.timeout` and SDK read timeout |
| Crawl call path | semaphore wait, start `call_tool`, status polls by job id, repeated status read after a timeout | each poll depends on the job id from the start response | event loop | sequential inside one call | same as search | none; no worker |
| Result parsing | JSON decode, dataclass build | needs its own response | inline on event loop | sequential after the call | none | short CPU; revisit if capture shows multi-megabyte bodies |
| Close | signal and await owner tasks | independent | event loop | concurrent (gather) | each task exits its own contexts | none; no worker |

Owner tasks exist because the SDK client holds a task group (a set of child tasks) that the same task must enter and exit.

**H. End-to-End Flow**
1. A caller (later `run_llm_metric_resolution`) calls `tool_gateway.open()`.
2. Two owner tasks connect; `verify_capabilities` runs `tools/list` on both and checks names.
3. Callers (later pipelines) call `search_web` and `crawl_site`, each bounded by its server's semaphore.
4. Each call uses the server's shared client, runs under timeout, retries transient failures, and returns a typed result or `ToolFailure`.
5. A crawl waits through its job id: a timed-out status read is asked again with the same id on the same client. No session is replaced.
6. The caller ends with `aclose()`; `AmenitySearch.aclose()` repeats it harmlessly.

## Layer 4: Backing

- **Owner task per server:** the locked same-task scope cannot be met from arbitrary tasks because of the SDK task group.
- **No session replacement:** a timeout stops our wait and does not break the session, so timeouts leave the session alone. V2a and V2b judge this, and a failure sends the shared-Client approach back for review, as locked.
- **No crawl re-issue:** a repeated `firecrawl_crawl` can start a second billed job. The job id belongs to the job on Firecrawl's side, so recovery asks again for that job, as locked.
- **Returned failures:** D5 says a failed item gets null and the run continues.
- **Client-boundary types:** nothing above the gateway imports `mcp`.
- **Optional keys:** keyless Parallel works at lower limits; keyless Firecrawl is caught by the capability check; M1 runs are unaffected.

---

## Open verification items

| Item | How it is closed |
| --- | --- |
| Parser shapes | capture one real `tools/call` body per server and fix the parsers; if keys or network are missing during Build, parsers ship against doc-shaped fixtures and this stays open |
| Rate-limit signal, crawl job id field name, status tool's job id argument name | read from the capture; confirm `firecrawl_crawl` returns the job id quickly on the hosted endpoint |
| V2a and V2b | run via runner flags (they spend credits); a failure sends the shared-Client approach back for review, as locked |
