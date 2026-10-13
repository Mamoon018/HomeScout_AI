# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl), Iteration 2

**Scope.** Iteration 2 of C3.1.1. The gateway built in iteration 1 (`search_web` and `crawl_site` over Parallel and Firecrawl) is extended to the new C3.1.1 spec in `R2_Mechanism_3_draft_spec.md`: M3 drives `firecrawl_map` and `firecrawl_scrape`; `firecrawl_crawl` is retained but unused by M3. The change points (A1 to A3, M1 to M4, R1, D1, D2) come from the "C3.1.1 Iteration Report: MCP Tool Gateway, old spec -> new spec". C3.1.2 onward (tool-schema building, phase gating, URL resolution, C3.2) is out of scope. Iteration 1 build-time corrections are not reopened: one owner task per server, no session replacement, `httpx2` as the HTTP client, unrecognised bodies de-masked into `ToolFailure(unparseable)`, `open()` tearing down on any non-local exit, `ValueError` on empty input.

**Status tags used below.** `[ADD]`, `[MODIFY]`, `[REMOVE]` carry the iteration-report ID. Untagged items are built and unchanged.

## Decisions taken for this revision

| ID | Topic | Decision | Basis |
| --- | --- | --- | --- |
| D1 | Session replacement | Not added. A timeout returns `ToolFailure` and the same session serves the next call. Crawl keeps its status re-read on the same `Client`. | User confirmed "keep as built". The status re-read needs no new session; map and scrape have no job id. The new spec sentence is stale pre-build text. |
| D2 | HTTP client library | `httpx2.AsyncClient` stays. The spec word `httpx` is treated as drift. | The approach (caller-owned client with the bearer header passed to `streamable_http_client`) is compatible; the library `httpx` is not, on mcp 2.2.0. The transport is written against `httpx2` types: it wraps responses in `httpx2.EventSource`, builds `httpx2.Headers` and `httpx2.URL`, and catches `httpx2.StreamError`. `httpx.AsyncClient` is not a subclass of `httpx2.AsyncClient`. Checked in source and installed classes; not run against a live server. |
| P1 | Probe target | New setting `FIRECRAWL_PROBE_URL`, default `https://example.com`. The probe maps and scrapes that one URL. | Spec names no URL. At `open()` no amenity URL exists yet. |
| P2 | Map and scrape timeouts | Module constants `MAP_TIMEOUT_SECONDS = 45.0`, `SCRAPE_TIMEOUT_SECONDS = 30.0`. Unmeasured, configurable. | Spec says scrape has "its own per-call timeout", no value. |
| P3 | Map and scrape retry | Retry on timeout, transport error, rate limit; waits 2 s then 3 s. | Both are idempotent reads; same set as `search_web`. |
| P4 | Scrape arguments | `url`, `formats: ["markdown"]`, `onlyMainContent: true`. | Spec lists `onlyMainContent` with no value; main content only keeps quotes free of navigation text. |
| P5 | Firecrawl semaphore | Renamed from crawl to Firecrawl. Value stays 2. | Spec: size to the vendor limit; confirm before raising. |
| P6 | Probe failure classes | Shape problem raises `McpToolUnavailableError`; a call that cannot complete after retries raises `McpConnectionError`. Both use `stage="verify_probe"`. | Spec names only the shape case; the other must also stop the run before amenity work. |

## Iteration point to plan section

| ID | Class | Where planned |
| --- | --- | --- |
| A1 | ADD | `map_site`: sections B, D, E, F, G; todos 5, 9, 10, 12 |
| A2 | ADD | `scrape_page`: sections B, D, E, F, G; todos 5, 9, 10, 12 |
| A3 | ADD | `_probe_firecrawl_shape` in `open`: sections D, E, F, G, H; todos 2, 3, 5, 9, 10, 12 |
| M1 | MODIFY | `verify_capabilities`: sections D, F, G; todos 5, 9, 12 |
| M2 | MODIFY | Firecrawl semaphore: sections D, Layer 3 G; todo 5 |
| M3 | MODIFY | V2b runner and fixtures: section 4; todos 9, 10, 12 |
| M4 | MODIFY (check only) | `_decode_body`: section F; one test in todos 9, 12 |
| R1 | REMOVE (code retained) | crawl and status requirement leaves `verify_capabilities`: sections D, F; todos 5, 9, 12 |

**Checked against the real SDK** (`mcp==2.2.0`, read in the installed environment):
- `Client(transport)` and `streamable_http_client(...)` are one-shot. The gateway never reconnects or replaces a `Client`: a timeout is our side giving up on waiting, so the open session stays in use.
- `Client` holds an anyio task group, so it must be exited in the task that entered it.
- The caller-owned HTTP client is `httpx2.AsyncClient` (`httpx2==2.12.0` is pinned). `httpx` 0.28.1 stays installed for other libraries and is not used here.
- `CallToolResult` fields are `content`, `structured_content` (wire name `structuredContent`), `is_error`. `_decode_body` already reads the real attribute, so M4 needs no code change.
- `Client` caches `tools/list` by default, so the capability check uses `cache_mode="bypass"`.
- Endpoints: Parallel `https://search.parallel.ai/mcp`; Firecrawl `https://mcp.firecrawl.dev/v2/mcp` (bearer). The `/v2/` segment is the hosted endpoint's name, not the MCP server package version; whether the server behind it returns the MCP server 3.x JSON output is settled at run time by the probe (open item OV-3).
- `mcp.server.MCPServer` serves in-process, so tests need no network.

## 0. Cross-mechanism check (updates to earlier mechanisms)

| Earlier piece | Finding | Action in this plan |
| --- | --- | --- |
| `AmenitySearch.__init__`, `aclose` (#6) | Holds `ToolGateway`; only calls `aclose()` on it today | No change. A bigger Protocol does not affect it. |
| Test fakes of `ToolGateway` | Existing tests pass `tool_gateway=None`; no fake implements the Protocol | No change to #7 and #8. |
| `Settings` | Has keys and URLs, no probe target | Add one optional field (todo 2) |
| `deep_search_context.md` C3.1.1 section | Describes the crawl-only gateway | Update Goal, capability check, operations, probe and V2b text; keep build-time notes (todo 11) |
| C3.1.2 plan text "web_search and firecrawl_crawl" | Historical wording of the C3.1.2 plan | Not touched; C3.1.3 re-plans the tool catalog |
| M6 `web_target` / `scrape_target` (RC10, built) | Gateway exposes typed ops, not tool names | Mapping from targets to gateway ops is C3.1.3 |
| Two gateway test files | Both build the Firecrawl fixture and call `open()` | Both must change (todos 9, 12); see F3 |

---

## 1. File and Module Structure (Build todos)

No prompt module: there is no LLM call. The gateway stays in `clients/`. No new source files: all new behaviour fits `clients/mcp_tools.py` and existing modules.

| # | File | Action | Purpose and ownership | IDs |
| --- | --- | --- | --- | --- |
| 1 | `backend/requirements.txt` | No change | `mcp`, `mcp-types`, `httpx2` already pinned | |
| 2 | `backend/src/core/config.py` | Modify | Add `firecrawl_probe_url` (`str`, default `https://example.com`); fix keyless comment | A3, M1 |
| 3 | `backend/.env.example` | Modify | Document `FIRECRAWL_PROBE_URL`; reword keyless Firecrawl comment | A3, M1 |
| 4 | `backend/src/exceptions/mcp.py` | Modify (docstrings only) | Module and `McpToolUnavailableError` docstrings cover a wrong output shape; no new class | A3, R1 |
| 5 | `backend/src/clients/mcp_tools.py` | Modify | Result contracts, Protocol members, `map_site`, `scrape_page`, probe, capability set, semaphore rename, parsers, log changes | A1 to A3, M1, M2, R1 |
| 6 | `backend/src/services/deep_search/amenity_search.py` | No change | Injection and `aclose` are unaffected | |
| 7 | `test_place_discovery.py`, `test_accessibility_enrichment.py`, `test_result_attachment.py` | No change | Pass `tool_gateway=None` | |
| 8 | `feature_sample_runs/result_attachment_sample_run.py` | No change | Passes `tool_gateway=None` | |
| 9 | `backend/tests/services/deep_search/test_mcp_tool_gateway.py` | Modify | Fixture server serves map and scrape; capability, probe, map, scrape, concurrency cases | A1 to A3, M1 to M4, R1 |
| 10 | `feature_sample_runs/mcp_tool_gateway_sample_run.py` | Modify | Add map and scrape stages; crawl becomes opt-in; V2b on scrapes | A1 to A3, M3 |
| 11 | `feature_context/deep_search_context.md` | Modify | C3.1.1 section brought to the new spec | all |
| 12 | `feature_tests/test_c3_1_1_mcp_tool_gateway.py` (not in iteration-1 plan; in repo) | Modify | Same fixture and case changes as #9 | A1 to A3, M1 to M4, R1 |
| 13 | `feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (not in iteration-1 plan; in repo) | Modify (docs) | Reword capability entries; add entries for the new cases | M1, R1, A1 to A3 |

Result contracts stay in `clients/mcp_tools.py`, not `schemas.py`, because `clients/` must not import `services/`.

---

## A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: DeepSearch (built in C3.1.2) sequences the responsibilities
   └─ Responsibility 2: AmenitySearch: find amenities and collect their facts
      └─ Mechanism 3 Workflow: run_llm_metric_resolution (later sub-components)
         └─ Component C3.1: evidence acquisition loop (later)
            └─ Sub-component C3.1.1 (this plan): MCP tool gateway, a client-boundary capability
               ├─ Stage 1: open, start both server sessions, one owner task each
               ├─ Stage 2: verify_capabilities, web_search + firecrawl_map + firecrawl_scrape   [M1, R1]
               ├─ Stage 3: probe Firecrawl output shape, one map and one scrape                  [A3]
               ├─ Stage 4: search_web, typed web_search on Parallel
               ├─ Stage 5: map_site, typed firecrawl_map on Firecrawl                            [A1]
               ├─ Stage 6: scrape_page, typed firecrawl_scrape on Firecrawl                      [A2]
               ├─ Stage 7: crawl_site and status re-read, retained and unused by M3
               └─ Stage 8: aclose, close every session in its owner task
```

C3.1.1 adds no workflow method to `AmenitySearch`. `run_llm_metric_resolution` will call `open` first and `aclose` last when built later.

## B. Data Contracts

| Contract | Purpose | Fields | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `McpServerConfig` | one server's connection settings | `name` · `url` · `api_key: str \| None` · `call_timeout_seconds` | immutable | factory → gateway |
| `SearchExcerpt`, `WebSearchResult` | search hit and outcome | unchanged | immutable | Stage 4 → C3.1.2+ |
| `CrawledPage`, `CrawlResult` | crawl page and outcome | unchanged (retained path) | immutable | Stage 7 → later |
| `MapLink` **[A1]** | one candidate page of a site | `url: str` · `title: str \| None` · `description: str \| None` | immutable | Stage 5 → C3.1.3/C3.1.6 |
| `MapResult` **[A1]** | typed map outcome | `url: str` (the mapped homepage) · `links: tuple[MapLink, ...]` · `retrieved_at: str` | immutable | Stage 5 → C3.1.3/C3.1.6 |
| `ScrapeResult` **[A2]** | typed scrape outcome | `url: str` (from `metadata.sourceURL`) · `text: str` (markdown) · `retrieved_at: str` | immutable | Stage 6 → C3.1.3/C3.1.6 |
| `ToolFailure` | typed per-call failure, returned not raised | `tool` · `kind: tool_error \| timeout \| rate_limited \| transport \| unparseable` · `message` | immutable | Stages 4 to 7 → callers |
| `McpGatewayError` tree | gateway-level failure, raised | `McpConnectionError`, `McpToolUnavailableError`; `stage` is `open`, `verify_capabilities` or `verify_probe` **[A3]** | immutable | Stages 1 to 3 → run |

> Rules: an empty `links` list is a valid `MapResult`, and empty `text` with a `sourceURL` is a valid `ScrapeResult`; neither is a failure, so C3.1.4 can label them `empty`. A scrape body with no non-empty `sourceURL` is `ToolFailure(unparseable)`. `ScrapeResult.url` is `metadata.sourceURL` as reported; per Firecrawl's docs that is the URL that was requested (the post-redirect URL is the separate `metadata.url`, which is not carried), so callers key by it as a stable page key (not live-verified). `retrieved_at` is stamped when the operation starts, as in `search_web`. No new failure kind. Keys appear only in `McpServerConfig.api_key`.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `ToolGateway` | Protocol | `open()` · `search_web(objective, search_queries)` · `map_site(url)` **[A1]** · `scrape_page(url)` **[A2]** · `crawl_site(url, limit, depth)` · `aclose()` | `McpToolGateway`, test fake | `AmenitySearch`; C3.1.3 to C3.1.7 later |
| `ClientFactory` | callable alias | `(McpServerConfig) -> async context manager yielding mcp.Client` | Streamable HTTP (default), in-process fake (tests) | `_ServerSession` |
| `mcp.Client` | external SDK | `list_tools(cache_mode)` · `call_tool(name, arguments, read_timeout_seconds)` | SDK | `_ServerSession`, `McpToolGateway` |
| `httpx2.AsyncClient` | external SDK | carries the `Authorization` header | SDK | default `ClientFactory` |
| `Settings` | existing config | keys, URLs, and `firecrawl_probe_url` **[A3]** | one | `create_mcp_tool_gateway` |

## D. Class & Method Blueprint

**`McpToolGateway`** implements `ToolGateway`; owns sessions, per-server semaphores, retry, timeouts, parsing.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` **[M2, A3]** | `(parallel: McpServerConfig, firecrawl: McpServerConfig, *, search_concurrency: int, firecrawl_concurrency: int, firecrawl_probe_url: str, client_factory: ClientFactory)` | hold configs, per-server semaphores, probe target, connect seam |
| `open` **[A3]** | `() -> None [raises: McpConnectionError, McpToolUnavailableError]` | start both sessions, verify capabilities, then probe Firecrawl |
| `verify_capabilities` **[M1, R1]** | `() -> None [raises: McpToolUnavailableError, McpConnectionError]` | list tools on both servers, match web_search, map, scrape |
| `_probe_firecrawl_shape` **[A3]** | `() -> None [raises: McpToolUnavailableError, McpConnectionError]` | map and scrape the probe URL, confirm MCP server 3.x JSON output shape |
| `search_web` | `(objective: str, search_queries: Sequence[str]) -> WebSearchResult \| ToolFailure [raises: ValueError, McpConnectionError]` | run `web_search` with retry, parse excerpts |
| `map_site` **[A1]** | `(url: str) -> MapResult \| ToolFailure [raises: ValueError, McpConnectionError]` | run `firecrawl_map` with retry, parse the link set |
| `scrape_page` **[A2]** | `(url: str) -> ScrapeResult \| ToolFailure [raises: ValueError, McpConnectionError]` | run `firecrawl_scrape` with retry, parse one page |
| `crawl_site` | `(url: str, limit: int, depth: int) -> CrawlResult \| ToolFailure [raises: ValueError, McpConnectionError]` | retained; start crawl, read the job by id |
| `aclose` | `() -> None` | idempotent; end every owner task |
| `_call_with_retry` **[A1, A2]** | `(semaphore, client, tool: str, arguments: dict, *, timeout: float, retry_kinds: set[str], target: str \| None = None) -> object \| ToolFailure` | one bounded call with transient retry; failure log names target |
| `_read_crawl_job` | `(client, job_id: str, url: str, retrieved_at: str) -> CrawlResult \| ToolFailure` | retained; poll or re-read the job by id |

**`_ServerSession`** (private) is unchanged: `start`, `client`, `stop`; one owner task per server.

**Module-level pure functions** (no state, tested from fixtures):

| Function | Signature | Purpose (one line) |
| --- | --- | --- |
| `_parse_search_result`, `_parse_crawl_result`, `_parse_crawl_status`, `_classify_failure`, `_decode_body` | unchanged | existing parsing and classification |
| `_parse_map_result` **[A1]** | `(result: CallToolResult, url: str, retrieved_at: str) -> MapResult [raises: _UnparseableResult]` | read `links` into typed candidates |
| `_parse_scrape_result` **[A2]** | `(result: CallToolResult, retrieved_at: str) -> ScrapeResult [raises: _UnparseableResult]` | read top-level `markdown` and `metadata.sourceURL` |
| `_log_attempt` **[A1, A2]** | `(tool: str, attempt: int, failure: ToolFailure, target: str \| None = None) -> None` | record one failed attempt as WARN |
| `create_mcp_tool_gateway` **[A3]** | `(settings: Settings) -> McpToolGateway` | composition root; opens nothing; passes probe URL |

**Module constants** **[A1, A2, M1, M2, R1]**: add map and scrape tool names, their argument tuples, `MAP_TIMEOUT_SECONDS`, `SCRAPE_TIMEOUT_SECONDS`, `FIRECRAWL_PROBE_URL_DEFAULT`; rename `CRAWL_CONCURRENCY` to `FIRECRAWL_CONCURRENCY`; remove `FIRECRAWL_CRAWL_ARGS` (no reader once the check drops crawl). Keep `FIRECRAWL_CRAWL_TOOL`, `FIRECRAWL_STATUS_TOOL`, `FIRECRAWL_STATUS_JOB_ARG` for the retained crawl path.

## E. Runtime Flow: Data Object Journey

Request path (runner and fixtures excluded). Unchanged stages are listed so the order is readable.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `open` → `_ServerSession.start` x2 | two `McpServerConfig` | one owner task and one `Client` per server | both sessions ready |
| 2 | `verify_capabilities` **[M1, R1]** | `tools/list` from each server | pass or `McpToolUnavailableError` | catalogs checked |
| 3 | `_probe_firecrawl_shape` **[A3]** | probe URL | one `map_site` and one `scrape_page`, run together; pass or raise | Firecrawl output shape confirmed |
| 4 | `search_web` | objective, queries | `WebSearchResult` or `ToolFailure` | typed excerpts |
| 5 | `map_site` **[A1]** | homepage url | `MapResult` or `ToolFailure` | typed candidate links |
| 6 | `scrape_page` **[A2]** | page url | `ScrapeResult` or `ToolFailure` | typed page keyed by source URL |
| 7 | `crawl_site`, `_read_crawl_job` | url, limit, depth | `CrawlResult` or `ToolFailure` (retained) | typed pages |
| 8 | `aclose` | all sessions | tasks ended, clients closed | gateway closed |

**Transformation trace (shape only):**
```
(url)                                                           # map_site  [A1]
 → arguments{ url }
 → [Firecrawl slot] → shared Client → call_tool("firecrawl_map") under MAP timeout
 → CallToolResult{ content[], structured_content?, is_error }
 → is_error or exception → ToolFailure{ tool, kind, message }   # transient kinds retry first
 | links list → MapResult{ url, links[MapLink], retrieved_at }   # empty list is valid
 | no links list, or only unusable entries → ToolFailure(unparseable)

(url)                                                           # scrape_page  [A2]
 → arguments{ url, formats=["markdown"], onlyMainContent=true }
 → [Firecrawl slot] → shared Client → call_tool("firecrawl_scrape") under SCRAPE timeout
 → CallToolResult
 → is_error or exception → ToolFailure
 | markdown + metadata.sourceURL → ScrapeResult{ url=sourceURL, text, retrieved_at }
 | no sourceURL, or no markdown → ToolFailure(unparseable)

(open)                                                          # probe  [A3]
 → gather( map_site(probe url), scrape_page(probe url) ), exceptions collected
 → both typed, scrape text non-empty            → proceed, log mcp.probe_passed
 | any ToolFailure(unparseable | tool_error) or empty text → McpToolUnavailableError(verify_probe)
 | any ToolFailure(timeout | transport | rate_limited)     → McpConnectionError(verify_probe)
```

**Approach at the real decision points:**
- Capability: Parallel needs `web_search(objective, search_queries)`; Firecrawl needs `firecrawl_map(url)` and `firecrawl_scrape(url, formats)`. Crawl and status tools are not checked. A miss raises `McpToolUnavailableError(stage="verify_capabilities")`.
- The probe runs only after the capability check passes, inside `open`'s teardown guard, so a probe failure closes both sessions before the exception leaves.
- Map and scrape retry on timeout, transport error and rate limit (2 s then 3 s). A non-rate-limit `is_error` makes one attempt. Exhaustion returns a `ToolFailure`.
- Only "cannot connect", "expected tool or argument missing" and "Firecrawl output shape not confirmed" raise. Everything else degrades per item (D5).
- The gateway never replaces a session or `Client` (D1). A timeout means our side stopped waiting; the session stays open. A dead session shows as repeated `ToolFailure(transport)` and is what V2a and V2b would reveal.

## F. Method Detail

**`verify_capabilities` [M1, R1]**
- **Purpose:** fail at connect, not mid-run, when a tool M3 drives is missing.
- **What it does:** list tools on both servers together with the cache bypassed; match `web_search` with its two arguments; match `firecrawl_map` with `url` and `firecrawl_scrape` with `url` and `formats`; do not look for crawl or status tools.
- **Failure:** `McpToolUnavailableError(stage="verify_capabilities")` for a missing tool or argument; `McpConnectionError` when a listing cannot be read. A missing Firecrawl key is not caught here: the session cannot open (401 per Firecrawl's changelog), so `open` raises `McpConnectionError(stage="open")` before this check (see OV-2).

**`_probe_firecrawl_shape` [A3]**
- **Purpose:** prove the endpoint returns the MCP server 3.x JSON output shape before any amenity work.
- **What it does:** call `map_site` and `scrape_page` on the probe URL together (they share no data); collect both outcomes even if one raises; classify the pair by the approach pointers in section E; do not rely on a declared `outputSchema`.
- **Pass condition:** a `MapResult` was parsed, and the `ScrapeResult` has a non-empty `text` and a non-empty `url`. A zero-link map is acceptable.
- **Failure:** shape problems raise `McpToolUnavailableError`; calls that cannot complete after their retries raise `McpConnectionError`; both carry `stage="verify_probe"` and name the operation and failure kind, never a body or a key.

**`map_site` [A1] and `scrape_page` [A2]**
- Validate first: `url` must be a non-empty `http(s)` URL (`ValueError`), matching `crawl_site`.
- Take a slot from the Firecrawl pool, reuse the one shared `Client`, wrap the call in `asyncio.timeout` and the SDK read timeout, map the outcome with `_classify_failure`, retry per P3, then parse inline.
- URLs are app-controlled: the LLM never supplies them (C3.1.3). The gateway does not host-filter or cap results; the 50-candidate cap and dedup are C3.1.6.

**`_parse_map_result` [A1]**
- Decode with `_decode_body`; require a mapping with a `links` list (a bare list body is not accepted).
- Each entry is an object with a string `url` (title and description optional) or a plain string; other entries are skipped and counted.
- Empty `links` returns an empty result. A non-empty list with no usable entry, or a body with no `links` list, raises `_UnparseableResult` (de-mask).

**`_parse_scrape_result` [A2]**
- Decode with `_decode_body`; require a mapping with a string top-level `markdown` and a string `metadata.sourceURL` that is non-empty after trimming.
- Empty `markdown` with a valid `sourceURL` returns an empty text. A body wrapped under `data`, missing `markdown`, or missing `sourceURL` raises `_UnparseableResult`. No older-shape tolerance is built.

**`_decode_body` [M4, check only]**
- Order stays: `structured_content`, then JSON-decode the text block. The attribute is the SDK's real field name, so nothing changes; one test pins it.

**`_call_with_retry` and `_log_attempt` [A1, A2]**
- Add an optional `target` carried only into the failure log; behaviour and retry rules unchanged. Failed attempts log at WARN (see section H).

**`crawl_site`, `_read_crawl_job`, `search_web`, `_ServerSession`** are unchanged. `crawl_site` and the status poll draw from the same Firecrawl pool, now named for Firecrawl **[M2]**.

---

## G. Drift entries (per method)

Scanned categories: input, preconditions, dependencies, concurrency, resources, time, side-effect completion. Evidence rule: the 3.x JSON shapes come from the server source (spec), not a live capture, so shape drift is handled by de-masking and settled by the probe, not by tolerant parsing.

### `map_site`
**Core behavior:** validate the URL, call `firecrawl_map` through the retry path, return typed candidates.
**Drifts handled:**
- **Bad input.** Empty or non-http(s) URL. Caught at the method entry. **Rejected** with `ValueError`.
- **Session not open.** Caught in the core via `client()`. **Propagated** as `McpConnectionError`.
- **Call fails, times out or is rate limited.** Handled in the shared call path. **Recovered** by retry (2 s, 3 s), then returned as `ToolFailure`.
- **Body in an unrecognised shape.** Handled in `_parse_map_result`. **Rejected** as `ToolFailure(unparseable)`, never an empty list.
**Left out (why):**
- Link dedup, host filtering, 50-link cap: C3.1.6 owns candidate shaping. *Wrong boundary.*
- Response-size cap: parse is inline and short; revisit only if a capture shows multi-megabyte bodies. *Not live.*
- Retry beyond the gateway: the loop-level retry belongs to C3.1.3/C3.1.6. *Wrong boundary.*

### `_parse_map_result`
**Core behavior:** turn a map body into `MapResult`.
**Drifts handled:**
- **Missing or non-list `links`.** Caught in the parser. **Rejected** (`_UnparseableResult`), so a shape miss is not read as "site has no pages".
- **A non-empty list with zero usable entries.** Same point. **Rejected**.
- **Some entries malformed.** Caught in the parser. **Recovered**: usable entries are kept, the rest skipped, and one WARN `mcp.map_links_skipped` records the count.
**Left out (why):**
- Tolerance for v1/v2 link shapes: the probe fails those at connect. *Trust (probe).*
- URL syntax validation of each link: C3.1.3 validates the chosen URL before it is scraped. *Wrong boundary.*

### `scrape_page`
**Core behavior:** validate, call `firecrawl_scrape` for markdown, return a page keyed by its source URL.
**Drifts handled:**
- **Bad input.** Same as `map_site`. **Rejected** (`ValueError`).
- **Session not open.** **Propagated**.
- **Call fails, times out or is rate limited.** Shared call path. **Recovered** by retry, then `ToolFailure`. A timeout leaves the session usable (D1).
- **Page returned with no `sourceURL` or no `markdown`.** `_parse_scrape_result`. **Rejected** as `ToolFailure(unparseable)`; M3 keys evidence by URL.
- **`sourceURL` differs from the request.** Not expected: per Firecrawl's docs `sourceURL` is the requested URL and the final URL is `metadata.url` (not live-verified). **Trusted and passed through**; the caller keys by the returned URL (handoff to C3.1.6).
**Left out (why):**
- Retry on empty markdown: an empty page is a final, valid answer. *Trust.*
- Stripping injected instructions from page text: C3.2's untrusted-content rule owns this. *Wrong boundary.*
- Anti-bot interstitial detection: indistinguishable here; the C3.2 verification gate rejects it. *Wrong boundary.*

### `_parse_scrape_result`
**Core behavior:** read top-level `markdown` and `metadata.sourceURL` into `ScrapeResult`.
**Drifts handled:**
- **Wrapped body (`data` envelope) or missing keys.** **Rejected** (`_UnparseableResult`), so an older shape fails loudly instead of yielding blank evidence.
- **Blank `sourceURL`.** **Rejected**; a blank key would collapse unrelated pages into one evidence slot.
**Left out (why):**
- Reading `data.markdown` as a fallback: spec says top-level and the probe guards the version. *Trust (probe).*

### `_probe_firecrawl_shape`
**Core behavior:** one map and one scrape of the probe URL; pass only on a typed pair with page text.
**Drifts handled:**
- **Wrong output shape.** Detected from the typed outcomes. **Rejected** with `McpToolUnavailableError(verify_probe)` before any amenity work.
- **Probe call cannot complete.** After the shared retries. **Propagated** as `McpConnectionError(verify_probe)`; the run cannot rely on Firecrawl.
- **One of the two raises while the other runs.** `gather` would otherwise leave the sibling orphaned. Handled in the core by collecting both outcomes, then re-raising the first exception. **Propagated**.
- **Probe target down.** A failing target looks like a tool error. Reported with the operation and kind so it is diagnosable. **Rejected** (accepted wording risk).
- **Cost.** Two billed calls per run. Accepted by spec; bounded by the shared pool and timeouts.
**Left out (why):**
- Fallback probe URL or probe caching across runs: no stated need; one setting is enough. *Imaginary.*
- Accepting the plain-text output of MCP server 1.x or 2.x: spec requires 3.x JSON output. *Trust.*

### `verify_capabilities`
**Core behavior:** match required tools and arguments on both servers.
**Drifts handled:**
- **Tool or argument renamed or removed.** Caught here. **Rejected** with `McpToolUnavailableError`.
- **Listing unreachable.** **Propagated** as `McpConnectionError`.
**Left out (why):**
- Crawl and status tool checks: M3 does not use them (R1). *Not live.*
- `onlyMainContent` argument check: spec requires only `url` and `formats`; the probe sends it and would fail loudly. *Trust (probe).*

### `open`
**Core behavior:** start both sessions, verify, probe.
**Drifts handled:**
- **Any failure or cancellation mid-open.** Handled in the existing guard. **Recovered** by closing both sessions, then **propagating**.
**Left out (why):**
- Partial open (Parallel only): a run needs both servers. *Trust.*

### `_call_with_retry` and `_log_attempt`
**Core behavior:** one bounded call with transient retry; log each failed attempt.
**Drifts handled:**
- **Semaphore held across a backoff sleep.** Already avoided: the slot is held only across the live call. *No change.*
**Left out (why):**
- Per-op retry tuning: one set of backoffs is enough until a capture shows otherwise. *Imaginary.*

### `create_mcp_tool_gateway`
**Core behavior:** build configs and the gateway from `Settings`; open nothing.
**Drifts handled:**
- **Blank probe URL setting.** Handled at the edge with the same blank-to-default treatment the key normaliser uses. **Recovered** to the default.
**Left out (why):**
- URL validation here: the probe's `map_site` call rejects a bad URL with `ValueError`. *Wrong boundary.*

---

## H. Logging

Per the diagnostic-logger skill: one stream of structured lines, boundary crossings, silent drifts and state changes only; nothing narrates success. All lines use `DEEP_SEARCH_LOGGER_NAME` and are JSON, as the existing `mcp.*` events are.

| Event | Level | Node type | Fields | When |
| --- | --- | --- | --- | --- |
| `mcp.session_opened` | INFO | boundary | `server`, `authenticated` | per server at open (unchanged) |
| `mcp.probe_passed` **[A3]** | INFO | boundary | `map_link_count`, `scrape_chars`, `scrape_url_matches_probe` | once per `open` after both probe calls are typed |
| `mcp.call_attempt_failed` **[A1, A2]** | WARN (was INFO) | silent drift (recover) | `tool`, `attempt`, `kind`, `message`, `target` (map and scrape) | each failed attempt, retried or final |
| `mcp.map_links_skipped` **[A1]** | WARN | silent drift (degrade) | `url`, `skipped`, `kept` | only when entries were skipped |

- **Rejects ride their exception.** Probe and capability failures are not logged again here; the exception message carries operation and kind, and the caller logs where it handles it.
- **Not logged:** every successful call, page text, link lists, anything derived from a key. The existing key-hygiene test keeps guarding keys and extends to the new tools.
- **Correlation.** Gateway lines carry `tool` and `target`. A per-amenity correlation id belongs to the pipeline that owns the amenity (C3.1.6/C3.1.7); the gateway has no amenity context. Handoff, not built here.
- **Level change.** A failed attempt that is retried is a handled drift, hence WARN. No test asserts the old INFO level.

---

## 4. Sample Runner and Fixture Set

### 4.1 Live sample runner (modify existing)

`feature_sample_runs/mcp_tool_gateway_sample_run.py`: manual, stage-by-stage, real servers, no LLM (so no prompt module and no worked-pair examples).

**How to run** from `backend/` (needs `PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`, network):
- `python -m src.services.deep_search.feature_sample_runs.mcp_tool_gateway_sample_run`
- Flags: `--v2a`, `--v2b`, `--crawl` (opt-in, spends credits), `--url <url>` (replaces `--crawl-url`; target for map, scrape and crawl).

**What it seeds:** the first place's `display_name.text` and `website_uri` from `data/m1_1_discovered_places.json`. M1.1 to M1.3 are not called. Objective and queries are hand-written. Map and scrape target the seeded website (or `--url`). For this run only, the connect-time probe targets the same URL (the runner overrides `FIRECRAWL_PROBE_URL`); production keeps the setting because no amenity URL exists when the gateway opens.

**What it prints:** one titled section per stage.

| Section | Content |
| --- | --- |
| INPUT STATE | seeded amenity, objective, queries, map and scrape url |
| STAGE 1, open | per server: connected, tool count, required tools found, key present; the `mcp.probe_passed` record **[A3]** |
| STAGE 2, `search_web` | request, excerpt count, first URLs, lengths, `retrieved_at`, or `ToolFailure` |
| STAGE 3, `map_site` **[A1]** | request, link count, first 5 links (url, title), `retrieved_at`, or `ToolFailure` |
| STAGE 4, `scrape_page` **[A2]** | the first mapped page: reported `url`, text length, `retrieved_at`, or `ToolFailure` |
| STAGE 5, `crawl_site` (only with `--crawl`) | page count, job id, or `ToolFailure` |
| STAGE 6, `aclose` | owner tasks ended, second `aclose` is a no-op |

Raw bodies and per-attempt records come from the `homescout.deep_search` logger via the collecting handler. On `McpGatewayError`: print class, `stage`, message, exit non-zero. A returned `ToolFailure` prints and gives non-zero exit at the end. Nothing is written to disk.

**Opt-in verification stages** (these spend credits):

| Flag | What it checks |
| --- | --- |
| `--v2a` | unchanged: ten concurrent searches match their own requests; one extra call cancelled mid-flight, others finish, follow-up works |
| `--v2b` **[M3]** | one `map_site`, then several concurrent `scrape_page` calls on mapped pages, each result checked against its own page; one extra scrape cancelled mid-flight, others finish, a follow-up scrape works on the same session |

### 4.2 Offline fixture set

Applies to both gateway test files (todos 9 and 12): pytest with the in-process `MCPServer` injected through the client factory. No network, no keys.

**Fixture server change [F3].** The Firecrawl fixture registers `firecrawl_map`, `firecrawl_scrape`, and (kept for the retained path) `firecrawl_crawl` and `firecrawl_check_crawl_status`. Default map and scrape handlers return MCP server 3.x JSON-shaped bodies, because every `open()` now probes. Toggles exist per tool so capability cases can drop one.

| Area | Assertion |
| --- | --- |
| Capabilities **[M1, R1]** | full set (web_search, map, scrape) passes; a server lacking crawl and status also passes; missing map, missing scrape, a missing `formats` argument, or a missing Parallel argument raises `McpToolUnavailableError(verify_capabilities)` |
| Probe pass **[A3]** | `open()` issues exactly one map and one scrape, after the capability check, and logs `mcp.probe_passed` |
| Probe shape fail **[A3]** | scrape body with no `sourceURL`, empty page text, or a wrapped `data` envelope raises `McpToolUnavailableError(verify_probe)` and leaves no running task |
| Probe call fail **[A3]** | persistent timeout or rate limit on the probe raises `McpConnectionError(verify_probe)` after the 2 s then 3 s backoffs |
| Map typed **[A1]** | object links, plain-string links and empty links parse; no `links` list gives `unparseable`; `is_error` returns `ToolFailure`, not raised; `retrieved_at` set |
| Map entries **[A1]** | malformed entries are skipped with one `mcp.map_links_skipped` record; all-malformed gives `unparseable` |
| Map arguments **[A1]** | exactly `url` is sent; bad URL raises `ValueError` before any call |
| Scrape typed **[A2]** | 3.x JSON body gives `ScrapeResult(url=sourceURL, text)`; empty markdown with a `sourceURL` is a valid empty result; missing `sourceURL` gives `unparseable` |
| Scrape arguments **[A2]** | `url`, `formats=["markdown"]`, `onlyMainContent=true` are sent; bad URL raises `ValueError` |
| Retry **[A1, A2]** | map and scrape retry twice with sleeps 2.0 then 3.0 on rate limit, then `ToolFailure`; non-transient `is_error` makes one attempt |
| Timeout **[A2, D1]** | a timed-out scrape returns `ToolFailure(timeout)`; the same `Client` serves the next call; no new `Client` is built |
| Concurrency **[M2, A2]** | several concurrent `scrape_page` calls each return their own page; in-flight Firecrawl calls (map, scrape, crawl) never exceed the pool size |
| Decode **[M4]** | when a result carries both structured content and a differing text block, the structured payload is used |
| Retained crawl | existing crawl, status re-read, deadline and argument cases keep passing unchanged against the extended fixture |
| Session scope, secrets | unchanged; the key-hygiene case also runs a map and a scrape |

---

# Architecture and Modularity Decisions

## Layer 1: Glance

**A. Architecture at a Glance**
- **Shape:** one concrete gateway behind one narrow Protocol, injected into `AmenitySearch`. Each server session lives in its own task. This iteration adds operations to the same gateway; no new component.
- **Seams (where things can change independently):**
  - Gateway contract: `ToolGateway`, so `AmenitySearch` and tests see no MCP types.
  - Connect step: client factory (Streamable HTTP in production, in-process in tests).
  - Server settings: URLs, keys and the probe URL from `Settings`.
- **Component list:** `ToolGateway`, `McpToolGateway`, `_ServerSession`, result dataclasses (now including `MapLink`, `MapResult`, `ScrapeResult`) and `ToolFailure`, `McpGatewayError` tree.

## Layer 2: Justification

**B. Component Map**

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `ToolGateway` | contract for the typed operations | result types | Yes: tests need no network |
| `McpToolGateway` | retry, timeout, semaphores, parsing, capability check, probe | `_ServerSession`, `ClientFactory` | implements |
| `_ServerSession` | one Client lifetime per server | `ClientFactory`, `mcp.Client` | none (concrete, private) |
| `McpServerConfig`, result types, `ToolFailure` | typed settings and outputs | none | none (frozen dataclasses) |
| `McpGatewayError` tree | connect, missing-tool and shape-not-confirmed exits with `stage` | none | none (exception tree) |

**C. Decisions & Justifications**

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| `map_site` and `scrape_page` as typed members of the existing Protocol | M3 drives map and scrape; callers must not parse content blocks | C3.1.3 would parse raw MCP bodies or use a second gateway |
| `MapLink`, `MapResult`, `ScrapeResult` frozen dataclasses | spec: "typed candidate list" and `(url, text)` | callers re-derive shape and can read `data.markdown` wrongly |
| `scrape_page` fails on a missing `sourceURL` | M3 keys and provenance-checks evidence by URL | blank or wrong keys collapse evidence from different pages |
| Probe as a private method of `open` | spec: confirm the 3.x JSON shape before amenity work | a wrong-version server fails mid-run with unparseable bodies |
| Probe runs map and scrape together | the two calls share no data | probe adds one extra serial round trip per run |
| Probe URL as a `Settings` field | spec names no URL; no amenity URL exists at `open` | a hard-coded URL cannot be changed without a code edit |
| One Firecrawl semaphore for map, scrape and crawl | spec: one semaphore per server | a second pool lets crawl and scrape together exceed the vendor limit |
| Capability check drops crawl and status | M3 does not use them (spec) | a map/scrape-only server is refused for a tool it never calls |
| `ToolFailure(unparseable)` reused for shape misses | no new reaction is needed downstream | a new kind forces every consumer to handle one more case |

**D. Kept Concrete / Rejected**

| Considered | Decision | Reason |
| --- | --- | --- |
| Reconnect or replace a session after a timeout or failure (D1) | rejected (unchanged) | a timeout means our side stopped listening; the session is still valid; crawl recovers by job id on the same `Client`; map and scrape have no job |
| Switch the HTTP client to `httpx` (D2) | rejected | the mcp 2.2.0 transport is written against `httpx2` types and methods |
| A probe class or probe module | not added | one private method; one caller |
| A separate gateway per tool or per server | rejected | logic is identical; one Protocol is enough |
| Generic "call any MCP tool" gateway | rejected | typed operations for four named tools only; no generic path needed |
| Tolerant parsing of MCP server 1.x/2.x map and scrape shapes | not added | spec requires 3.x JSON output; the probe fails older shapes at connect |
| Probe result caching or a fallback probe URL | not added | no stated requirement; one probe per `open` |
| New exception class for the shape failure | not added | `McpToolUnavailableError` already means "required capability not available" |
| New `ToolFailure` kind for map and scrape | not added | `unparseable` already carries the reaction |
| Host filtering and 50-link cap in the gateway | not added | C3.1.6 owns candidate shaping |
| Retry library | not added | two fixed backoffs |
| Parallel `session_id`, `web_fetch` | not added | unchanged: ignored on paid keys; locked unused |
| Thread or process offload for parsing | not added | small inline JSON; revisit if a capture shows multi-megabyte map bodies |
| New source files | not created | all new code fits `clients/mcp_tools.py` and existing modules |

**Over-engineering guard: every element retained in this iteration and its one-line justification**

| Element | One-line justification |
| --- | --- |
| `ToolGateway` Protocol members `map_site`, `scrape_page` | callers depend on typed operations, not MCP content blocks |
| `MapLink`, `MapResult`, `ScrapeResult` | spec requires typed results; callers key by URL and need fixed fields |
| `FIRECRAWL_PROBE_URL` setting | the probe target must be changeable without a code edit and no amenity URL exists at `open` |
| `target` field in the failure log | ties a failed attempt to its page, since gateway lines carry no other page identity |
| `MAP_TIMEOUT_SECONDS`, `SCRAPE_TIMEOUT_SECONDS` | spec requires scrape's own timeout; map is bounded the same way |

## Layer 3: Wiring

**E. Dependency Direction**
```
AmenitySearch → [ToolGateway] ← McpToolGateway → _ServerSession → mcp.Client → httpx2.AsyncClient
McpToolGateway → McpServerConfig, result types, McpGatewayError
create_amenity_search → create_mcp_tool_gateway → Settings (keys, URLs, probe url)
```

**F. Composition Root**
- **Where:** `create_amenity_search(settings)` in `amenity_search.py`, which calls `create_mcp_tool_gateway(settings)` in `clients/mcp_tools.py`.
- **Selects:** keys, URLs and the probe URL from `Settings`; module-constant starting values (unmeasured, configurable): search timeout 30 s, map timeout 45 s, scrape timeout 30 s, crawl per-call 60 s, crawl overall deadline 180 s, retry waits 2 s then 3 s, crawl poll 3 s, search semaphore 4, Firecrawl semaphore 2.
- **Lifecycle:** the factory opens nothing. `open()` runs at the start of `run_llm_metric_resolution` and `aclose()` at its end. `AmenitySearch.aclose()` also closes the gateway (covers a leaked session). Probe runs inside `open`.

**G. Async Execution Map** (placement set by blocking behavior, ordering by data dependency, decided separately)

| Operation group | Operations and I/O | Data dependency | Placement | Ordering | Shared-state handling | Blocking / worker |
| --- | --- | --- | --- | --- | --- | --- |
| Session open | HTTP connect, MCP handshake per server | independent | event loop, one owner task per server | concurrent (gather of the two ready signals) | each owner task writes only its own session | none; no worker |
| Capability check | `list_tools` per server | independent; needs open sessions | event loop | concurrent (gather) | read only | none; no worker |
| Firecrawl probe **[A3]** | `map_site` and `scrape_page` on the probe URL | independent of each other; needs verified capabilities | event loop | concurrent (gather, exceptions collected); probe starts after the check | each call returns a value; no shared writes | none; every call under `asyncio.timeout` and SDK read timeout |
| Search call path | semaphore wait, `call_tool`, backoff sleep | retry depends on previous attempt | event loop | sequential inside one call; calls from different amenities gathered by the caller (later) | per-server semaphore bounds in-flight; results returned | none; every call under timeout |
| Map and scrape call path **[A1, A2]** | semaphore wait, `call_tool`, backoff sleep | retry depends on previous attempt; map and scrape of different pages are independent | event loop | sequential inside one call; scrapes of different pages gathered by the caller (C3.1.6 Phase 2) | one Firecrawl pool bounds in-flight map, scrape and crawl; results returned | none; every call under timeout |
| Crawl call path | semaphore wait, start `call_tool`, status polls by job id | each poll depends on the job id | event loop | sequential inside one call | same pool as above | none; no worker |
| Result parsing | JSON decode, dataclass build | needs its own response | inline on event loop | sequential after the call | none | short CPU; revisit if a capture shows multi-megabyte map bodies |
| Close | signal and await owner tasks | independent | event loop | concurrent (gather) | each task exits its own contexts | none; no worker |

Owner tasks exist because the SDK client holds a task group (a set of child tasks) that the same task must enter and exit. All operations use the async-native `httpx2` client, so nothing is offloaded to a thread or process.

**H. End-to-End Flow**
1. A caller (later `run_llm_metric_resolution`) calls `tool_gateway.open()`.
2. Two owner tasks connect; `verify_capabilities` checks `web_search`, `firecrawl_map`, `firecrawl_scrape` with their arguments.
3. The probe maps and scrapes the probe URL together and confirms the 3.x JSON shape, or `open` closes both sessions and raises.
4. Callers (later pipelines) call `search_web`, `map_site` and `scrape_page`, each bounded by its server's semaphore. `crawl_site` stays available but unused by M3.
5. Each call uses the server's shared client, runs under timeout, retries transient failures, and returns a typed result or `ToolFailure`.
6. The caller ends with `aclose()`; `AmenitySearch.aclose()` repeats it harmlessly.

## Layer 4: Backing

- **Owner task per server:** the locked same-task scope cannot be met from arbitrary tasks because of the SDK task group.
- **No session replacement:** a timeout stops our wait and does not break the session; V2a and V2b judge this, and a failure sends the shared-Client approach back for review, as locked. D1 confirmed this for iteration 2.
- **`httpx2` stays:** the SDK transport, its error types and its SSE reader are `httpx2`; D2.
- **Probe before work:** a wrong output shape would otherwise appear as `unparseable` on every Phase 2 call of every amenity. One connect-time check costs two calls per run.
- **Returned failures:** D5 says a failed item gets null and the run continues. Only connect, capability and shape failures stop the run.
- **Client-boundary types:** nothing above the gateway imports `mcp`.
- **Optional keys:** keyless Parallel works at lower limits; Firecrawl needs a key (hosted keyless access was removed per its changelog, so the session cannot open and `open` raises `McpConnectionError`; not verified live); M1 runs are unaffected because the gateway opens nothing at construction.

---

## Open verification items

| ID | Item | How it is closed |
| --- | --- | --- |
| OV-1 | Parser shapes for map and scrape | the probe confirms the 3.x JSON shape at connect; capture one real map and one real scrape body with the runner and fix the parsers if keys differ |
| OV-2 | Missing-key behaviour of the hosted endpoint | run the runner without `FIRECRAWL_API_KEY`; expect `McpConnectionError(stage="open")` (401). If it connects and lists fewer tools instead, update the missing-key comments in `config.py`, `.env.example` and `exceptions/mcp.py` |
| OV-3 | Probe passes on the configured `/v2/mcp` endpoint | run the runner; if the probe reports an unexpected shape, change `FIRECRAWL_MCP_URL` or the probe URL setting |
| OV-4 | Map and scrape timeout values, Firecrawl pool size | measure on the runner; confirm the vendor limit before raising the pool above 2 |
| OV-5 | Rate-limit signal, crawl job id field, status tool argument name | retained crawl path only; read from a capture if crawl is re-enabled |
| OV-6 | V2a and V2b | run via runner flags (they spend credits); a failure sends the shared-Client approach back for review, as locked |

## Handoffs to later sub-components

| To | What the gateway guarantees or leaves to it |
| --- | --- |
| C3.1.3 | passes app-injected homepage URL to `map_site` and the id-resolved URL to `scrape_page`; the gateway does no host check |
| C3.1.4 | empty `links` and empty `text` arrive as valid results, never failures; timeouts and parse misses arrive as `ToolFailure` |
| C3.1.6 | applies the 50-candidate cap, URL dedup and fan-out; keys evidence by the returned `ScrapeResult.url` (per Firecrawl's docs the requested URL; not live-verified) |
| C3.1.6/C3.1.7 | owns the per-amenity correlation id for log lines; counts gateway-internal retries when it reasons about call caps |

---

# Appendix: C3.1.1 Iteration Report: MCP Tool Gateway, old spec -> new spec

This is the stage-one report (per `skills/iteration_report.md`) that this plan implements. It is kept as
delivered, with three updates for accuracy: the plan-mode "Deliverable" lines are dropped, and the three
places that said D1 and D2 were still waiting now point to their resolutions in "Decisions taken for this
revision" at the top of this file (D1: keep as built; D2: keep `httpx2`).

## Report context

Sub-component C3.1.1 (MCP tool gateway for Parallel and Firecrawl) was already built. The new
Mechanism 3 draft spec changes its Firecrawl side: M3 now drives `firecrawl_map` + `firecrawl_scrape`
instead of `firecrawl_crawl`. The report states which points are added, modified or removed, which
artifacts each touches, and how the flow changes. It does **not** write the implementation plan or any
code; this file above it is that plan.

**How to read the traceflows:** each one is a top-down tree, and the status tag sits in one aligned
column at the right of each diagram. `◄── NEW` = added, `◄── CHANGED` = altered, `◄── GONE` =
removed. BEFORE and AFTER are stacked, each scoped to its own point.

---

## Report 1. Confirmation

- **Read:** the skill; old spec (`deep_search_context.md` L2773-2813); old implementation plan
  (`r2_mechanism_3_c3_1_1_implementation_plan.md`); new spec (`R2_Mechanism_3_draft_spec.md`
  C3.1.1 L101-131, plus cross-references at L30, L53, L163-167, L193, L344, L493-497).
- **"Implemented"** = old spec + old plan **including its build-time corrections**:
  (a) one owner task per server (the SDK `Client` holds an anyio task group);
  (b) the gateway never reconnects or replaces a session ("replaced by reconnecting" was dropped);
  (c) the caller-owned HTTP client is `httpx2.AsyncClient`, not `httpx`;
  (d) the status tool is a required capability; (e) unrecognised bodies are de-masked into
  `ToolFailure(unparseable)`; (f) `open()` tears both sessions down on any non-local exit;
  (g) `search_web` rejects empty input with `ValueError`.
- **Repo was available.** I checked `src/clients/mcp_tools.py`, `src/exceptions/mcp.py`,
  `src/core/config.py` and the tests against the plan; they match it.
- **Naming convention.** `#n` = item number in the old plan's file table (#1 requirements.txt,
  #2 config.py, #3 .env.example, #4 exceptions/mcp.py, #5 clients/mcp_tools.py, #6 amenity_search.py,
  #7 three existing test files, #8 result_attachment_sample_run.py, #9 test_mcp_tool_gateway.py,
  #10 mcp_tool_gateway_sample_run.py, #11 deep_search_context.md).
  `(new spec)` = name stated by the new spec but absent from the plan.
  `(illustrative)` = name I chose, or a symbol that exists in code but is not in the plan.
- **Not in the old plan but present in the repo:** `feature_tests/test_c3_1_1_mcp_tool_gateway.py`
  (T1-T24) and `feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md`. Marked
  `(illustrative, not in plan)` below; see F12.
- **Result:** 3 ADD, 4 MODIFY, 1 REMOVE, 2 DECISION-GATED, plus an Unchanged list.

---

## Report 2. Current traceflow, with change locations

```
run_llm_metric_resolution          (planned in C3.1.7, not built yet)
│
└─ McpToolGateway                   (clients/mcp_tools.py, #5)
   │
   ├─ open()
   │    ├─ start sessions: Parallel + Firecrawl
   │    └─ verify_capabilities                     ◄── M1, R1, A3
   │          Parallel : web_search
   │          Firecrawl: firecrawl_crawl + firecrawl_check_crawl_status
   │
   ├─ search_web(objective, queries) ──► WebSearchResult | ToolFailure
   │
   ├─ crawl_site(url, limit, depth) ──► CrawlResult | ToolFailure
   │     └─ takes a slot from the Firecrawl pool   ◄── M2
   │
   ├─ map_site(url)       attaches here            ◄── A1
   ├─ scrape_page(url)    attaches here            ◄── A2
   │
   └─ aclose()
```

Also touched outside this flow: the `ToolGateway` Protocol gains two members (A1, A2);
`_decode_body` is checked (M4); the V2b runner and fixtures change (M3); a reconnect step would sit
in `_ServerSession` (D1); the HTTP client factory is in question (D2).

| ID | Class | Summary |
|----|-------|---------|
| A1 | ADD | `map_site(url)` over `firecrawl_map`: typed link candidate list |
| A2 | ADD | `scrape_page(url)` over `firecrawl_scrape`: one typed page keyed by `metadata.sourceURL` |
| A3 | ADD | Connect-time live probe that confirms the Firecrawl MCP server 3.x JSON output shape |
| M1 | MODIFY | Capability check: Firecrawl must expose `firecrawl_map` + `firecrawl_scrape` |
| M2 | MODIFY | The single Firecrawl semaphore now guards map/scrape (crawl retained) |
| M3 | MODIFY | V2b verification moves from concurrent crawls to concurrent scrapes after a map |
| M4 | MODIFY | Confirm the real structured-content attribute name (check only) |
| R1 | REMOVE | Crawl and crawl-status tools no longer required at connect (code retained) |
| D1 | DECISION-GATED | New spec: failed session "replaced by reconnecting"; the build dropped that |
| D2 | DECISION-GATED | New spec says `httpx`; the build corrected this to `httpx2` |

---

## Report 3. ADD points

### A1: `map_site(url)` over `firecrawl_map`

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `ToolGateway` Protocol | add: a `map_site(url)` member returning a typed map result or `ToolFailure`, so callers and injected fakes see the Firecrawl map operation without any MCP types. |
| mcp_tools.py (#5) · `McpToolGateway.map_site` (new spec) | add: validate the URL, call `firecrawl_map` through the existing retry, timeout and semaphore path, parse the body, and return the typed result or a `ToolFailure`. The URL is app-injected; the LLM never supplies it. |
| mcp_tools.py (#5) · map result contracts (illustrative `MapResult`, `MapLink`) | add: frozen typed values holding the homepage url, the candidate links (url, optional title and description) and `retrieved_at`. They sit beside `CrawlResult` because `clients/` must not import `services/`. |
| mcp_tools.py (#5) · map parser (illustrative) | add: read `links` (an array of `{url, title?, description?}`; a plain-string form is tolerated) through the shared `_decode_body` (illustrative). An unreadable body becomes `ToolFailure(unparseable)`, not an empty list. |
| mcp_tools.py (#5) · Firecrawl name constants (illustrative) | add: the `firecrawl_map` tool name and its `url` argument beside the existing `FIRECRAWL_*` constants, so M1 and the call share one definition. |
| test_mcp_tool_gateway.py (#9) and feature_tests/test_c3_1_1_mcp_tool_gateway.py (illustrative, not in plan) | add: map fixtures on the in-process Firecrawl server (object links, string links, empty links, `is_error`, unrecognised body) plus retry, timeout and semaphore cases for this op. |
| mcp_tool_gateway_sample_run.py (#10) | add: a stage that maps the seeded place's website and prints the link count and first URLs. |
| deep_search_context.md (#11) | modify: the C3.1.1 text and cross-mechanism note, so the context file lists `map_site`. |
| config.py (#2), exceptions/mcp.py (#4) | check only: no new setting or exception type expected. |

BEFORE
```
McpToolGateway
├─ search_web(...)
├─ crawl_site(...)
└─ aclose()
```

AFTER
```
McpToolGateway
├─ search_web(...)
├─ crawl_site(...)                         kept, unused by M3
├─ map_site(url)                                              ◄── NEW
│    ├─ validate the url                                      ◄── NEW
│    ├─ wait for a Firecrawl slot                             ◄── NEW
│    ├─ call firecrawl_map, with retry                        ◄── NEW
│    └─ read the links field                                  ◄── NEW
│         ├─ readable    ──► MapResult(links, retrieved_at)   ◄── NEW
│         └─ unreadable  ──► ToolFailure(unparseable)         ◄── NEW
└─ aclose()
```

Behaviour change: callers can ask for a site's link set as a typed candidate list, with no page
content and no crawl job, or get a typed failure.

### A2: `scrape_page(url)` over `firecrawl_scrape`

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `ToolGateway` Protocol | add: a `scrape_page(url)` member returning one typed page or a `ToolFailure`. |
| mcp_tools.py (#5) · `McpToolGateway.scrape_page` (new spec) | add: validate the URL, call `firecrawl_scrape` with `formats: ["markdown"]` and `onlyMainContent`, parse, and return the page or a failure. It uses its own per-call timeout (see F7). The URL is app-resolved from the LLM's `id` upstream (C3.1.3). |
| mcp_tools.py (#5) · scrape result contract (illustrative `ScrapeResult`) | add: a frozen `(url, text, retrieved_at)` value where `url` comes from `metadata.sourceURL`, so M3 can key and provenance-check evidence by URL. |
| mcp_tools.py (#5) · scrape parser (illustrative) | add: read the unwrapped top-level `markdown` and `metadata.sourceURL` (not `data.markdown`). A body with no non-empty `sourceURL` is a failure, because M3 keys evidence by that URL. |
| mcp_tools.py (#5) · Firecrawl name constants (illustrative) | add: the `firecrawl_scrape` tool name, its `url` and `formats` arguments, and its timeout value. |
| both gateway test files (#9; illustrative, not in plan) | add: scrape fixtures (3.x JSON shape, missing `sourceURL`, empty markdown with a `sourceURL`, `is_error`, timeout then next call works). |
| mcp_tool_gateway_sample_run.py (#10) | add: a stage that scrapes one mapped page and prints url, text length and `retrieved_at`. |
| deep_search_context.md (#11) | modify: add the scrape operation and its parse rule to the C3.1.1 text. |

BEFORE
```
McpToolGateway
├─ search_web(...)
├─ crawl_site(...)          the only way to get page content
└─ aclose()
```

AFTER
```
McpToolGateway
├─ search_web(...)
├─ crawl_site(...)                         kept, unused by M3
├─ scrape_page(url)                                           ◄── NEW
│    ├─ validate the url                                      ◄── NEW
│    ├─ wait for a Firecrawl slot                             ◄── NEW
│    ├─ call firecrawl_scrape (markdown, onlyMainContent)     ◄── NEW
│    └─ read markdown + metadata.sourceURL                    ◄── NEW
│         ├─ sourceURL present  ──► ScrapeResult(url, text)   ◄── NEW
│         └─ sourceURL missing  ──► ToolFailure               ◄── NEW
└─ aclose()
```

Behaviour change: callers get one page's markdown keyed by its source URL, or a typed failure,
without starting a crawl job.

### A3: Connect-time Firecrawl shape probe

Depends on A1 and A2 (it calls both); it can be reverted on its own.

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `McpToolGateway.open` | add: a step after `verify_capabilities` that runs the probe, so a wrong-version endpoint fails before any amenity work. Existing teardown on any non-local exit already covers the new failure. |
| mcp_tools.py (#5) · probe step (illustrative) | add: one `map_site` and one `scrape_page` against a known page, confirming non-empty page text, a non-empty `metadata.sourceURL` and parseable `links`. A different shape raises `McpToolUnavailableError`. `outputSchema` is not relied on. |
| mcp_tools.py (#5) · module docstring "only two conditions raise" | modify: a third raise condition (wrong output shape) now exists. |
| exceptions/mcp.py (#4) · `McpToolUnavailableError` | check only: reused; the `stage` value for a probe miss is unspecified (F2). |
| config.py (#2), .env.example (#3) | check only: the probe's target URL is not named by the spec; a setting may be needed (F2). |
| both gateway test files (#9; illustrative, not in plan) | add: probe pass and probe fail cases. modify: **every** test that calls `open()` against the fixture Firecrawl server must now serve 3.x JSON-shaped map and scrape bodies. |
| mcp_tool_gateway_sample_run.py (#10) · STAGE 1 | modify: print the probe outcome next to the capability table. |

BEFORE
```
open()
├─ start sessions: Parallel + Firecrawl
├─ verify_capabilities
└─ ready
```

AFTER
```
open()
├─ start sessions: Parallel + Firecrawl
├─ verify_capabilities
├─ shape probe                                                          ◄── NEW
│    ├─ map_site(probe url)                                             ◄── NEW
│    ├─ scrape_page(first mapped page)                                  ◄── NEW
│    ├─ shape matches    ──► continue                                   ◄── NEW
│    └─ any other shape  ──► McpToolUnavailableError                    ◄── NEW
│                              └─ open() closes both sessions, raises   ◄── NEW
└─ ready
```

Behaviour change: a Firecrawl endpoint that returns the wrong output shape now fails at connect;
every run pays one extra map and one extra scrape call at `open()`.

---

## Report 4. MODIFY points

### M1: Capability check requires `firecrawl_map` and `firecrawl_scrape`

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `verify_capabilities` | modify: the Firecrawl required set gains `firecrawl_map` (arg `url`) and `firecrawl_scrape` (args `url`, `formats`). The Parallel `web_search` requirement is untouched. A miss still raises `McpToolUnavailableError(stage="verify_capabilities")`. |
| mcp_tools.py (#5) · required-name constants (illustrative) | modify: add the map and scrape tool and argument tuples that the check reads. The crawl constants stay (see R1). |
| test_mcp_tool_gateway.py (#9) · capability tests | modify: the "full set passes", "missing tool" and "missing argument" cases must build the Firecrawl fixture with map and scrape. |
| feature_tests/test_c3_1_1_mcp_tool_gateway.py (illustrative, not in plan) | modify: the same capability entries (T1-T5). |
| mcp_tool_gateway_sample_run.py (#10) · STAGE 1 | modify: the capability table prints map and scrape presence. |
| .env.example (#3), config.py (#2) · keyless comment | modify (inferred): the comment says a keyless Firecrawl "has no crawl tool"; the new check is about map and scrape, and that claim was unverified (F5). Resolved: the comments now say a missing key stops the session from opening (401 per Firecrawl's changelog; not verified live). |

BEFORE
```
verify_capabilities
├─ Parallel : web_search
│       needs: objective, search_queries
└─ Firecrawl
     ├─ firecrawl_crawl
     │      needs: url, limit, maxDiscoveryDepth, allowExternalLinks
     └─ firecrawl_check_crawl_status
            needs: id
```

AFTER
```
verify_capabilities
├─ Parallel : web_search
│       needs: objective, search_queries
└─ Firecrawl
     ├─ firecrawl_map             ◄── NEW
     │      needs: url            ◄── NEW
     ├─ firecrawl_scrape          ◄── NEW
     │      needs: url, formats   ◄── NEW
     ├─ firecrawl_crawl                       (still here; see R1)
     └─ firecrawl_check_crawl_status          (still here; see R1)
```

Behaviour change: a Firecrawl server missing map or scrape now fails at connect.

### M2: Firecrawl semaphore guards map and scrape

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `McpToolGateway.__init__` (`crawl_concurrency`, `_crawl_sem`) | modify: the one per-server Firecrawl slot pool is now what map and scrape calls draw from (C3.1.7 L344: "replacing the old crawl semaphore"). The role changes; renaming the crawl-named attribute is (inferred). |
| mcp_tools.py (#5) · composition constants (`CRAWL_CONCURRENCY`, illustrative) | modify: the starting value 2 was sized for crawls; it must be re-checked against up to 8 concurrent scrapes per amenity (F8). |
| mcp_tools.py (#5) · `create_mcp_tool_gateway` | check only: builds the gateway with the constants; no change unless the keyword is renamed. |
| both gateway test files (#9; illustrative, not in plan) | modify: the "in-flight never exceeds semaphore" case is extended to map and scrape on the Firecrawl pool. |

BEFORE
```
Firecrawl slot pool            size 2, named for crawl
└─ used by
     └─ crawl_site and its status polls
```

AFTER
```
Firecrawl slot pool            size still open (F8)   ◄── CHANGED
└─ used by
     ├─ map_site                                      ◄── NEW
     ├─ scrape_page                                   ◄── NEW
     └─ crawl_site and its status polls       kept
```

Behaviour change: Firecrawl throughput for M3 is bounded by this pool, so its size now limits
Phase-2 scraping rather than crawls.

### M3: V2b verification moves to the scrape path

| Artifact | Change |
|---|---|
| mcp_tool_gateway_sample_run.py (#10) · `--v2b` | modify: replace "two concurrent crawls, a capability call during a crawl, forced crawl timeout" with "several concurrent `scrape_page` calls after one `map_site`; each result matches its page; one forced scrape timeout does not fail the others; the session stays usable". Crawl-interference checks apply only to retained `crawl_site`. |
| mcp_tool_gateway_sample_run.py (#10) · `--crawl-url` | modify (inferred): the URL now seeds map and scrape; the flag name is stale. |
| both gateway test files (#9; illustrative, not in plan) | modify: add scrape equivalents of the concurrency and forced-timeout cases (same `Client` serves the next call, no new `Client` built). |
| deep_search_context.md (#11) · V2b bullet | modify: the V2b text under C3.1.1. |

BEFORE
```
V2b check (Firecrawl)
├─ run two crawls at the same time
├─ call a fast tool while a crawl runs
└─ force one crawl to time out
     └─ re-read that crawl by its job id
          └─ other calls and the session must still work
```

AFTER
```
V2b check (Firecrawl, M3 path)                           ◄── CHANGED
├─ map_site once                                         ◄── NEW
├─ scrape_page for several pages at the same time        ◄── NEW
│    └─ each result must match its own page              ◄── NEW
└─ force one scrape to time out                          ◄── NEW
     └─ the other scrapes must still succeed             ◄── NEW
          └─ the same session must serve the next call   ◄── NEW
(crawl-interference checks stay only for the retained crawl_site)
```

Behaviour change: the manual verification now proves the shared `Client` under the calls M3
actually makes.

### M4: Confirm the structured-content attribute name (check only)

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `_decode_body` (illustrative) | check only: confirm it reads the attribute the SDK really exposes. Old plan section 0 says `CallToolResult` has `structured_content` in mcp==2.2.0, so no change is expected (F6). |
| both gateway test files (#9; illustrative, not in plan) | add (inferred): one case where structured content and text differ, proving the structured path is the one used. |

BEFORE
```
_decode_body(result)
├─ structured payload present  ──► use it
└─ otherwise                   ──► JSON-decode the text block
```

AFTER
```
_decode_body(result)
├─ structured payload present  ──► use it
│       attribute name checked against the SDK   ◄── CHANGED (check only)
└─ otherwise                   ──► JSON-decode the text block
```

Behaviour change: none expected; the worry that the structured payload is silently skipped is
closed by a check.

---

## Report 5. REMOVE points

### R1: Crawl and crawl-status tools no longer required at connect

Code fate: retained (only the connect-time requirement goes; `crawl_site` stays).

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `verify_capabilities` | remove: the `firecrawl_crawl` (4 args) and `firecrawl_check_crawl_status` (`id`) requirements, because M3 does not use them. A server lacking them now passes. The status tool is dropped by implication (inferred). |
| mcp_tools.py (#5) · `FIRECRAWL_CRAWL_*`, `FIRECRAWL_STATUS_*` (illustrative) | check only: still used by retained `crawl_site` and `_read_crawl_job`. Whether `FIRECRAWL_CRAWL_ARGS` stays once nothing checks it is open. |
| test_mcp_tool_gateway.py (#9) · "missing status tool raises", "keyless without crawl tool raises" | remove or reword: they assert a connect-time raise that no longer happens. |
| feature_tests/test_c3_1_1_mcp_tool_gateway.py (illustrative, not in plan) | remove or reword: the matching T-entries. |
| deep_search_context.md (#11) · capability bullet | modify: drop crawl and status from the required list. |

BEFORE
```
Firecrawl server does not list firecrawl_crawl
└─ open()
     └─ verify_capabilities
          └─ McpToolUnavailableError, caught at connect
```

AFTER
```
Firecrawl server does not list firecrawl_crawl
└─ open()
     └─ verify_capabilities
          ├─ crawl no longer required             ◄── GONE
          └─ open() passes
               └─ later crawl_site(...) call
                    └─ ToolFailure at call time   ◄── CHANGED
```

Behaviour change: a missing crawl tool is no longer caught at connect; a later caller of the
retained `crawl_site` would see it as a per-call failure.

---

## Report 6. DECISION-GATED points

### D1: Replace a failed or timed-out session by reconnecting

New spec (L127): "A timed-out/failed session is replaced by reconnecting in the owning task."
Old spec (L2806) and plan (section D rejected row, Layer 4) record this as **corrected in the
build and rejected**: a timeout is our side giving up one wait; the session stays valid.

AS BUILT
```
a call times out
└─ ToolFailure(timeout) is returned
     └─ the same open session serves the next call
          └─ a dead session shows as repeated ToolFailure(transport)
```

IF INTENDED
```
a call times out, or the session fails
└─ gateway replaces the session by reconnecting, in the owner task   ◄── NEW
     ├─ builds a new Client (the SDK Client is one-shot)             ◄── NEW
     └─ calls still in flight on the old Client must be handled      ◄── NEW
touches: _ServerSession (replace step), _single_call / _call_with_retry,
         tests on forced timeout and session usable, V2a/V2b runner,
         the rejected-options table of the old plan
```

Not planned for when the report was written. **Resolved: keep as built.** The status re-check runs on the
same `Client` and map and scrape have no job id, so no session replacement is added (see "Decisions
taken for this revision", D1).

### D2: HTTP client library (`httpx` vs `httpx2`)

New spec (L107): "The `httpx` client that carries the `Authorization` header." The build corrected
this: mcp 2.x depends on `httpx2`, so the caller-owned client is `httpx2.AsyncClient`.

AS BUILT
```
_streamable_http_factory
└─ httpx2.AsyncClient(headers: Authorization: Bearer ...)
     └─ streamable_http_client(url, http_client=...) ──► mcp.Client
```

IF INTENDED
```
_streamable_http_factory
└─ httpx.AsyncClient(headers: Authorization: Bearer ...)   ◄── CHANGED
     └─ streamable_http_client(url, http_client=...) ──► mcp.Client
touches: _TRANSPORT_ERRORS (httpx2.HTTPError), requirements.txt (#1),
         tests that use the factory, the SDK notes of the old plan
```

Not planned for when the report was written. **Resolved: keep `httpx2`.** The approach is compatible; the
`httpx` library is not, because the mcp 2.2.0 transport is written against `httpx2` types (see "Decisions
taken for this revision", D2).

---

## Report 7. Unchanged

- `search_web` operation, its retry set (timeout, transport, rate limit) and its parser. The new
  spec confirms the Parallel body matches the existing parser (`results[]`, `excerpts` list).
- Typed results or typed `ToolFailure`; failures returned, not raised; keys never logged.
- Session scope (open at the start of `run_llm_metric_resolution`, close at its end, not in a
  constructor; `aclose()` closes a leaked session) and the owner task per server.
- High-level `Client` wrapper over `streamable_http_client(url, http_client=...)`; bearer keys
  from `Settings`; `ToolGateway` Protocol as the test seam.
- Error typing: `McpConnectionError` and `McpToolUnavailableError`, each with `stage`.
- Retained crawl path: `crawl_site`, both result shapes, the longer crawl timeout, re-read by job
  id, never re-issued (now explicitly "retained, unused by M3").
- One shared `Client` per server, one semaphore per server (the rule), explicit timeouts, no
  sharing across threads or loops.
- V2a (ten concurrent `web_search` calls).
- `AmenitySearch` injection and `aclose` (#6), the three existing test files and
  `result_attachment_sample_run.py` that pass `tool_gateway=None` (#7, #8), `requirements.txt` (#1).

---

## Report 8. Component traceflow after all points

```
run_llm_metric_resolution                   (planned in C3.1.7)
│
└─ McpToolGateway
   │
   ├─ open()
   │    ├─ start sessions: Parallel + Firecrawl        unchanged
   │    ├─ verify_capabilities
   │    │     Parallel : web_search                    unchanged
   │    │     Firecrawl: firecrawl_map(url)                 ◄── M1
   │    │                firecrawl_scrape(url, formats)     ◄── M1
   │    │                crawl + status: not required       ◄── R1
   │    └─ shape probe: map_site + scrape_page              ◄── A3
   │          wrong shape ──► McpToolUnavailableError       ◄── A3
   │
   ├─ search_web(...)                                 unchanged
   ├─ map_site(url)     ──► MapResult | ToolFailure         ◄── A1
   ├─ scrape_page(url)  ──► ScrapeResult | ToolFailure      ◄── A2
   ├─ crawl_site(...)   retained, unused by M3              ◄── R1
   │
   │   Firecrawl slot pool shared by map / scrape / crawl   ◄── M2
   │   structured-payload attribute confirmed               ◄── M4
   │   V2b check = concurrent scrape_page after one map     ◄── M3
   │
   └─ aclose()                                        unchanged

Resolved after the report was delivered:
   D1  failed session replaced by reconnecting?   no, keep as built
   D2  httpx or httpx2 for the HTTP client?       keep httpx2
```

---

## Report 9. Flags

| #   | Flag |
|-----|------|
| D1  | New spec re-introduces "replaced by reconnecting", which the build explicitly rejected and removed. Resolved: keep as built. |
| D2  | New spec says `httpx`; the build recorded `httpx2` as a correction. Resolved: keep `httpx2`; spec wording is drift. |
| F1  | `onlyMainContent` is listed for `firecrawl_scrape` with no value (presumably true). Only `url` and `formats` are capability-checked, so a server that lacks `onlyMainContent` passes connect. |
| F2  | The probe's target URL, whether it needs a setting, which `stage` a probe miss reports, and whether a probe call that fails (rather than returns a wrong shape) raises `McpToolUnavailableError` or `McpConnectionError` are all unspecified. Every run also pays one map and one scrape at `open()`. |
| F3  | Every offline test that calls `open()` must now serve 3.x JSON-shaped map and scrape bodies, because `open()` probes. This is the widest supporting-artifact ripple. |
| F4  | `firecrawl_mcp_url` defaults to `https://mcp.firecrawl.dev/v2/mcp` while the spec requires MCP server 3.x JSON output. Research found the `/v2/` segment is the endpoint's name, not the MCP server version; whether the server behind it returns that shape is settled by the probe. |
| F5  | The spec said a missing map/scrape "also catches a missing key", but its research note did not name the 3 tools a keyless endpoint exposed. Resolved by later research: per Firecrawl's 3.29.1 changelog hosted keyless access was removed (401), so a missing key fails at session open (`McpConnectionError`, stage `open`), not at the capability check. Not verified live. |
| F6  | New spec: code reads snake_case `structured_content`, "if the SDK exposes camelCase" it returns None. Old plan section 0 says mcp==2.2.0 `CallToolResult` has `structured_content`. The two documents disagree; likely already satisfied. |
| F7  | "M3 scrape uses its own per-call timeout" has no value. Today `McpServerConfig` holds one per-server timeout (Firecrawl: 60 s) and the crawl deadline is 180 s. A per-op value needs a source. Map's timeout is unstated. |
| F8  | Semaphore size (value 2, named for crawl) versus up to 8 concurrent scrapes per amenity across concurrent pipelines. The spec says "confirm vendor rate limit before raising"; no value given. |
| F9  | Retry accounting: gateway-internal retries (2 s, 3 s) stack under C3.1.3's "each scrape + one retry". C3.1.3's caps count only calls that hit the gateway, so real MCP requests can exceed its stated worst case. Retry kinds for map/scrape are not stated (inferred: same set as search; both are idempotent reads). |
| F10 | Empty versus failed at the gateway boundary: the spec only says "no `sourceURL` is a failure". Inferred: empty `links`, or empty `markdown` with a `sourceURL`, is a valid empty result (C3.1.4 needs this to label `empty`), and a body with no `links` key is `unparseable`. |
| F11 | The gateway returns the full link set; the 50-candidate cap is C3.1.6, not here (inferred). URL validation for map/scrape (http(s), non-empty, `ValueError`) is unstated; inferred to mirror `crawl_site`. |
| F12 | Two gateway test files plus a test-plan doc exist; only one test file is in the old plan. All fixture changes (M1, A3, R1) land in both unless one is retired. |
| F13 | Stale text carried into the new spec: "R2 has no MCP client ... no `mcp` dependency, no server keys" (already built), and the old plan's rejected-options reason "only two tools are needed" (now four typed operations; the typed-ops decision still holds). |
| F14 | Old open-verification items are narrowed: parser shapes are closed for Parallel and map/scrape (new spec, verified); the crawl job-id field and status-tool argument name stay open for the retained crawl path only. |

---

## Report self-check (against the skill's "Before answering")

- Every new-spec C3.1.1 requirement is in exactly one point or in Unchanged: ops (A1, A2), parsing
  (A1, A2), probe (A3), capability set (M1, R1), decode attribute (M4), semaphore (M2), V2b (M3),
  reconnect (D1), `httpx` (D2); everything else is in Report 7.
- Every old-spec requirement is in Unchanged, MODIFY or REMOVE (crawl requirement -> R1, V2b -> M3,
  semaphore role -> M2, reconnect -> D1).
- Every artifact comes from the plan or is labelled `(new spec)` or `(illustrative)`.
- Every point has BEFORE/AFTER and a `Behaviour change` line; no code, no implementation steps.
- The implementation plan is the main body of this file; D1 and D2 were resolved before it was written.
