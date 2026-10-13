# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl), Iteration 3

**Scope.** Iteration 3 of C3.1.1. The gateway built in iteration 2 (`search_web`, `map_site`, `scrape_page`, retained `crawl_site`, and the connect-time Firecrawl shape probe) is corrected and extended to the "Fixes to be incorporated in iteration" section of the C3.1.1 spec (`deep_search_context.md` L2810-2825). Those fixes were identified after a live `--v2a` sample run failed at the probe: the `firecrawl_map` response did not stream back within the httpx client's **default 5.0 s read timeout**, the SDK's GET-based SSE resume was refused `405`, and the resulting `MCPError` was misclassified `tool_error` (not retried) and surfaced as a misleading `McpToolUnavailableError(verify_probe)`. The change points (A4; M5 to M10) come from the "C3.1.1 Iteration Report: built spec -> Fixes" appended at the end of this file. C3.1.2 onward (tool-schema building, phase gating, URL resolution, C3.2) is out of scope. Iteration 1 and 2 build-time corrections are not reopened: one owner task per server, no session replacement (D1), `httpx2` as the HTTP client (D2), unrecognised bodies de-masked into `ToolFailure(unparseable)`, `open()` tearing down on any non-local exit, `ValueError` on empty input. Iteration-2 points (A1 to A3, M1 to M4, R1) stay as built; their tags remain in the body for provenance.

**Iteration 3 change points (this revision).**

| ID | Class | Summary |
| --- | --- | --- |
| A4 | ADD | `batch_scrape(urls)` over Firecrawl batch scrape: one job, many pages, keyed by `metadata.sourceURL` |
| M5 | MODIFY | Explicit read timeout on the httpx2 client in `_streamable_http_factory` (was httpx default 5 s) |
| M6 | MODIFY | `_classify_failure` maps `MCPError` (SSE-ended / reconnect-exhausted) to `transport` |
| M7 | MODIFY | `_classify_failure` reaches `rate_limited` for a `429` even when wrapped in `MCPError` |
| M8 | MODIFY | Lengthen the retry backoff so a `rate_limited` retry clears Firecrawl's per-minute window |
| M9 | MODIFY | Cap gateway submission concurrency to the vendor plan limit (`FIRECRAWL_CONCURRENCY`) |
| M10 | MODIFY | Per-call timeouts account for Firecrawl's queue-inclusive job clock |

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

### Decisions taken for iteration 3 (the fixes)

| ID | Topic | Decision | Basis |
| --- | --- | --- | --- |
| P7 | httpx read timeout (M5) | `_streamable_http_factory` builds `httpx2.AsyncClient(timeout=httpx2.Timeout(connect=10.0, read=None, write=10.0, pool=10.0))`. `read=None` so the transport never severs a live SSE stream; duration is governed in one place by the per-call `asyncio.timeout` and SDK `read_timeout_seconds`. connect/write/pool stay bounded so a dead TCP connect fails fast. | The default 5 s httpx read timeout severed a map that streamed for >5 s; the call budget, not a transport default, must bound the stream. Consistent with D2 (`httpx2`). |
| P8 | `MCPError` classification (M6) | `_classify_failure` treats `mcp.shared.exceptions.MCPError` (SSE-ended / reconnection-exhausted) as `transport`, so it is retried on the same session and, if persistent, returns `ToolFailure(transport)`; a probe disconnect becomes `McpConnectionError(verify_probe)`. | A dropped stream is a transport fault, not a tool error; it must retry and read honestly. A retry reissues the call on the same `Client` (a new request stream), so D1 (no session replacement) holds. |
| P9 | 429 inside `MCPError` (M7) | `_classify_failure` checks the rate-limit signal **first**: `status_code == 429` on the exception or its `response`, **or** a case-insensitive match of `{429, "rate limit", "too many requests", "retry-after"}` in `str(exc)` including when wrapped in `MCPError`; only then does the generic `MCPError`(SSE-ended) branch return `transport`. If the SDK exposes `status_code==429`, the existing branch already covers it (check only). | Rate/queue limits must retry as rate limits, not drop as `tool_error`, and a 429-bearing `MCPError` must not be mis-read as a plain disconnect. SDK opacity is an open item (OV-7). |
| P10 | Rate-limit backoff (M8) | Split the backoff by kind. `timeout`/`transport` keep `(2.0, 3.0)` (brief blips, retry fast). `rate_limited` honors a `Retry-After` value when the response carries one, else uses `(30.0, 60.0)`; retry count stays at 2 (3 attempts), so the hard-throttle worst case adds about 90 s. The per-minute figure the window is sized against is an open item (OV-8). | Two short waits both fall inside the same throttled minute and are wasted; a rate-limited retry must approach a 60 s window. |
| P11 | Submission concurrency (M9) | `FIRECRAWL_CONCURRENCY = 2` (the Free plan's concurrent-browser limit); `SEARCH_CONCURRENCY = 4` is unchanged (Parallel is a separate server). A4's per-job `BATCH_MAX_CONCURRENCY = 2` (one batch uses the full plan parallelism; the docs warn a low value slows large batches). Joint rule: at 2 + 2, a batch overlapping a single scrape can request up to 4 browsers; the excess only queues (not a 429), so C3.1.6 runs one batch **or** singles per amenity, not both, keeping our self-queue near zero (OV-9). | Over-submitting self-queues work whose wait is charged against each job's timeout; the cap and batch `maxConcurrency` must not jointly exceed the plan. |
| P12 | Queue-aware timeouts (M10) | Starting values (unmeasured, configurable): `MAP_TIMEOUT_SECONDS = 60.0`, `SCRAPE_TIMEOUT_SECONDS = 60.0` (both raised to cover a short queue behind a busy pool), `BATCH_DEADLINE_SECONDS = 300.0` with a 5 s poll interval, `SEARCH_TIMEOUT_SECONDS = 30.0` unchanged (Parallel has no queue model), the retained `CRAWL_DEADLINE_SECONDS = 180.0` kept, `CRAWL_CALL_TIMEOUT_SECONDS = 60.0` kept. Firecrawl's one clock runs submission to execution (48 h ceiling), so each budget leaves room for queue wait without orphaning a job past its own timeout. Values confirmed on the runner (OV-10). | A job still queued under the 2-browser limit must not be dropped by us too early, nor awaited long past Firecrawl's own timeout. |
| P13 | Batch scrape (A4) | Add `batch_scrape(urls, formats=["markdown"])`: start a batch job, poll by job id (reusing the `crawl_site` / `_read_crawl_job` start-then-poll shape), parse the job envelope's `data[]` into a list of the existing `ScrapeResult` under a new `BatchScrapeResult` wrapper, follow the `next` cursor, and tolerate per-URL partial failures. Per-job `maxConcurrency` stays within the plan. `scrape_page` is kept for single-page and the probe. Batch is **not** added to the connect-time capability check (user decision): `verify_capabilities` stays `web_search` + `firecrawl_map` + `firecrawl_scrape`, and a missing or renamed batch tool surfaces as a per-call `ToolFailure` on the first `batch_scrape`, like the retained `crawl_site`. | A site deep-search scrapes several pages; one batch job is one submission and one job clock instead of N calls serialized by the 2-browser pool. The authenticated MCP session exposes a batch tool (confirmed by the domain owner); the exact tool name and arguments are read from the authenticated `tools/list` at build time so A4 binds to the real name, not a guessed one (OV-11). |

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
| A4 | ADD | `batch_scrape`: sections B, C, D, E, F, G; todos 5, 9, 10, 12 |
| M5 | MODIFY | `_streamable_http_factory` timeout: sections D, F, G; todos 5, 9, 12 |
| M6 | MODIFY | `_classify_failure` MCPError->transport: sections D, E, F, G; todos 5, 9, 12 |
| M7 | MODIFY | `_classify_failure` 429-in-MCPError->rate_limited: sections F, G; todos 5, 9, 12 |
| M8 | MODIFY | retry backoff values: sections D, F; todos 5, 9, 12 |
| M9 | MODIFY | `FIRECRAWL_CONCURRENCY` sizing: sections D, Layer 3 G; todo 5 |
| M10 | MODIFY | queue-aware per-call timeouts: sections D, F, G; todos 5, 9, 12 |

**Checked against the real SDK** (`mcp==2.2.0`, read in the installed environment):
- `Client(transport)` and `streamable_http_client(...)` are one-shot. The gateway never reconnects or replaces a `Client`: a timeout is our side giving up on waiting, so the open session stays in use.
- `Client` holds an anyio task group, so it must be exited in the task that entered it.
- The caller-owned HTTP client is `httpx2.AsyncClient` (`httpx2==2.12.0` is pinned). `httpx` 0.28.1 stays installed for other libraries and is not used here.
- `CallToolResult` fields are `content`, `structured_content` (wire name `structuredContent`), `is_error`. `_decode_body` already reads the real attribute, so M4 needs no code change.
- `Client` caches `tools/list` by default, so the capability check uses `cache_mode="bypass"`.
- Endpoints: Parallel `https://search.parallel.ai/mcp`; Firecrawl `https://mcp.firecrawl.dev/v2/mcp` (bearer). The `/v2/` segment is the hosted endpoint's name, not the MCP server package version; whether the server behind it returns the MCP server 3.x JSON output is settled at run time by the probe (open item OV-3).
- `mcp.server.MCPServer` serves in-process, so tests need no network.
- **Iteration 3 transport facts (from the live trace that motivated the fixes):** the hosted Firecrawl transport is a long-lived SSE stream; the caller-owned `httpx2.AsyncClient` built with no `timeout` applies httpx's default 5.0 s read timeout to the SSE response, so a tool call that streams for longer raises `httpx2.ReadTimeout`; the SDK then resumes via an HTTP `GET` to the same endpoint, which Firecrawl answers `405 Method Not Allowed`, and after `MAX_RECONNECTION_ATTEMPTS` it raises `mcp.shared.exceptions.MCPError("SSE stream ended and reconnection attempts were exhausted")`. `_classify_failure` does not recognise `MCPError`, so it returns `tool_error`. These are the facts M5-M7 act on.

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
| 5 | `backend/src/clients/mcp_tools.py` | Modify | Result contracts, Protocol members, `map_site`, `scrape_page`, probe, capability set, semaphore rename, parsers, log changes; **iteration 3:** httpx timeout in `_streamable_http_factory`, `_classify_failure` MCPError/429 handling, backoff values, `FIRECRAWL_CONCURRENCY` sizing, queue-aware timeouts, new `batch_scrape` op + `BatchScrapeResult` + batch parser + batch tool constants | A1 to A3, M1, M2, R1, A4, M5 to M10 |
| 6 | `backend/src/services/deep_search/amenity_search.py` | No change | Injection and `aclose` are unaffected | |
| 7 | `test_place_discovery.py`, `test_accessibility_enrichment.py`, `test_result_attachment.py` | No change | Pass `tool_gateway=None` | |
| 8 | `feature_sample_runs/result_attachment_sample_run.py` | No change | Passes `tool_gateway=None` | |
| 9 | `backend/tests/services/deep_search/test_mcp_tool_gateway.py` | Modify | Fixture server serves map and scrape; capability, probe, map, scrape, concurrency cases; **iteration 3:** slow-stream-survives-timeout, MCPError->transport retry, 429-in-MCPError->rate_limited, longer backoff values, queue-aware timeout, batch-job fixtures | A1 to A3, M1 to M4, R1, A4, M5 to M10 |
| 10 | `feature_sample_runs/mcp_tool_gateway_sample_run.py` | Modify | Add map and scrape stages; crawl becomes opt-in; V2b on scrapes; **iteration 3:** a `batch_scrape` stage over mapped pages (the transport/call/header diagnostic tracers added this session already live here behind `--trace-calls`) | A1 to A3, M3, A4 |
| 11 | `feature_context/deep_search_context.md` | Modify | C3.1.1 section brought to the new spec | all |
| 12 | `feature_tests/test_c3_1_1_mcp_tool_gateway.py` (not in iteration-1 plan; in repo) | Modify | Same fixture and case changes as #9 | A1 to A3, M1 to M4, R1, A4, M5 to M10 |
| 13 | `feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (not in iteration-1 plan; in repo) | Modify (docs) | Reword capability entries; add entries for the new cases; **iteration 3:** entries for M5-M10 and A4 | M1, R1, A1 to A3, A4, M5 to M10 |

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
               ├─ Stage 6b: batch_scrape, one firecrawl batch job over many URLs               [A4]
               ├─ Stage 7: crawl_site and status re-read, retained and unused by M3
               └─ Stage 8: aclose, close every session in its owner task
```

Iteration-3 fixes attach to the shared machinery under these stages, not as new stages: the client factory's read timeout [M5], the failure classifier [M6, M7], the retry backoff [M8], the Firecrawl slot pool size [M9], and the per-call timeout budgets [M10] all sit on the call path every Firecrawl stage uses.

C3.1.1 adds no workflow method to `AmenitySearch`. `run_llm_metric_resolution` will call `open` first and `aclose` last when built later.

## B. Data Contracts

| Contract | Purpose | Fields | Mutability | Created by → Read by |
| --- | --- | --- | --- | --- |
| `McpServerConfig` | one server's connection settings | `name` · `url` · `api_key: str \| None` · `call_timeout_seconds` | immutable | factory → gateway |
| `SearchExcerpt`, `WebSearchResult` | search hit and outcome | unchanged | immutable | Stage 4 → C3.1.2+ |
| `CrawledPage`, `CrawlResult` | crawl page and outcome | unchanged (retained path) | immutable | Stage 7 → later |
| `MapLink` **[A1]** | one candidate page of a site | `url: str` · `title: str \| None` · `description: str \| None` | immutable | Stage 5 → C3.1.3/C3.1.6 |
| `MapResult` **[A1]** | typed map outcome | `url: str` (the mapped homepage) · `links: tuple[MapLink, ...]` · `retrieved_at: str` | immutable | Stage 5 → C3.1.3/C3.1.6 |
| `ScrapeResult` **[A2]** | typed scrape outcome | `url: str` (from `metadata.sourceURL`) · `text: str` (markdown) · `retrieved_at: str` | immutable | Stage 6 and 6b → C3.1.3/C3.1.6 |
| `BatchScrapeResult` **[A4]** | typed batch-scrape outcome (job wrapper) | `pages: tuple[ScrapeResult, ...]` (one per returned page, each keyed by its own `sourceURL`) · `total: int` · `completed: int` · `failed_urls: tuple[str, ...]` (per-URL partial failures) · `retrieved_at: str` | immutable | Stage 6b → C3.1.6 |
| `ToolFailure` | typed per-call failure, returned not raised | `tool` · `kind: tool_error \| timeout \| rate_limited \| transport \| unparseable` · `message` | immutable | Stages 4 to 7 → callers |
| `McpGatewayError` tree | gateway-level failure, raised | `McpConnectionError`, `McpToolUnavailableError`; `stage` is `open`, `verify_capabilities` or `verify_probe` **[A3]** | immutable | Stages 1 to 3 → run |

> Rules: an empty `links` list is a valid `MapResult`, and empty `text` with a `sourceURL` is a valid `ScrapeResult`; neither is a failure, so C3.1.4 can label them `empty`. A scrape body with no non-empty `sourceURL` is `ToolFailure(unparseable)`. `ScrapeResult.url` is `metadata.sourceURL` as reported; per Firecrawl's docs that is the URL that was requested (the post-redirect URL is the separate `metadata.url`, which is not carried), so callers key by it as a stable page key (not live-verified). `retrieved_at` is stamped when the operation starts, as in `search_web`. No new failure kind (`BatchScrapeResult` reuses `ScrapeResult` per page and `ToolFailure` for a whole-job failure). Keys appear only in `McpServerConfig.api_key`.
>
> **Iteration 3 [A4] rule:** `BatchScrapeResult` is a job wrapper, not a per-page type: each element of its `pages` is the existing `ScrapeResult`, keyed by the page's own `metadata.sourceURL` (not request order). A page that failed inside an otherwise-completed job is recorded in `failed_urls` (the batch's own error listing), not as a whole-job `ToolFailure`; an unreadable job envelope is `ToolFailure(unparseable)`.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `ToolGateway` | Protocol | `open()` · `search_web(objective, search_queries)` · `map_site(url)` **[A1]** · `scrape_page(url)` **[A2]** · `batch_scrape(urls)` **[A4]** · `crawl_site(url, limit, depth)` · `aclose()` | `McpToolGateway`, test fake | `AmenitySearch`; C3.1.3 to C3.1.7 later |
| `ClientFactory` | callable alias | `(McpServerConfig) -> async context manager yielding mcp.Client` | Streamable HTTP (default), in-process fake (tests) | `_ServerSession` |
| `mcp.Client` | external SDK | `list_tools(cache_mode)` · `call_tool(name, arguments, read_timeout_seconds)` | SDK | `_ServerSession`, `McpToolGateway` |
| `httpx2.AsyncClient` **[M5]** | external SDK | carries the `Authorization` header; built with an explicit `timeout` (read bound matched to the call budget, not httpx's 5 s default) | SDK | default `ClientFactory` |
| `Settings` | existing config | keys, URLs, and `firecrawl_probe_url` **[A3]** | one | `create_mcp_tool_gateway` |

## D. Class & Method Blueprint

**`McpToolGateway`** implements `ToolGateway`; owns sessions, per-server semaphores, retry, timeouts, parsing.

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `__init__` **[M2, A3, M9]** | `(parallel: McpServerConfig, firecrawl: McpServerConfig, *, search_concurrency: int, firecrawl_concurrency: int, firecrawl_probe_url: str, client_factory: ClientFactory)` | hold configs, per-server semaphores (Firecrawl pool sized to the plan browser limit [M9]), probe target, connect seam |
| `open` **[A3]** | `() -> None [raises: McpConnectionError, McpToolUnavailableError]` | start both sessions, verify capabilities, then probe Firecrawl |
| `verify_capabilities` **[M1, R1]** | `() -> None [raises: McpToolUnavailableError, McpConnectionError]` | list tools on both servers, match web_search, map, scrape |
| `_probe_firecrawl_shape` **[A3]** | `() -> None [raises: McpToolUnavailableError, McpConnectionError]` | map and scrape the probe URL, confirm MCP server 3.x JSON output shape |
| `search_web` | `(objective: str, search_queries: Sequence[str]) -> WebSearchResult \| ToolFailure [raises: ValueError, McpConnectionError]` | run `web_search` with retry, parse excerpts |
| `map_site` **[A1]** | `(url: str) -> MapResult \| ToolFailure [raises: ValueError, McpConnectionError]` | run `firecrawl_map` with retry, parse the link set |
| `scrape_page` **[A2]** | `(url: str) -> ScrapeResult \| ToolFailure [raises: ValueError, McpConnectionError]` | run `firecrawl_scrape` with retry, parse one page |
| `batch_scrape` **[A4]** | `(urls: Sequence[str], *, formats: Sequence[str] = ("markdown",)) -> BatchScrapeResult \| ToolFailure [raises: ValueError, McpConnectionError]` | start one batch job over many URLs, poll by id, parse the job envelope |
| `crawl_site` | `(url: str, limit: int, depth: int) -> CrawlResult \| ToolFailure [raises: ValueError, McpConnectionError]` | retained; start crawl, read the job by id |
| `aclose` | `() -> None` | idempotent; end every owner task |
| `_call_with_retry` **[A1, A2]** | `(semaphore, client, tool: str, arguments: dict, *, timeout: float, retry_kinds: set[str], target: str \| None = None) -> object \| ToolFailure` | one bounded call with transient retry; failure log names target |
| `_read_crawl_job` | `(client, job_id: str, url: str, retrieved_at: str) -> CrawlResult \| ToolFailure` | retained; poll or re-read the job by id |
| `_read_batch_job` **[A4]** | `(client, job_id: str, retrieved_at: str) -> BatchScrapeResult \| ToolFailure` | poll the batch job by id, follow the `next` cursor to the end |

**`_ServerSession`** (private) is unchanged: `start`, `client`, `stop`; one owner task per server.

**Module-level pure functions** (no state, tested from fixtures):

| Function | Signature | Purpose (one line) |
| --- | --- | --- |
| `_parse_search_result`, `_parse_crawl_result`, `_parse_crawl_status`, `_decode_body` | unchanged | existing parsing and classification |
| `_classify_failure` **[M6, M7]** | `(error_or_result) -> ToolFailureKind` | map an exception or `is_error` result to a kind; now classifies `MCPError`(SSE-ended) as `transport` and a `429` embedded in an `MCPError` as `rate_limited` |
| `_streamable_http_factory` **[M5]** | `(config: McpServerConfig) -> AbstractAsyncContextManager[Client]` | default client factory; builds `httpx2.AsyncClient` with an explicit `timeout` matched to the call budget |
| `_parse_map_result` **[A1]** | `(result: CallToolResult, url: str, retrieved_at: str) -> MapResult [raises: _UnparseableResult]` | read `links` into typed candidates |
| `_parse_scrape_result` **[A2]** | `(result: CallToolResult, retrieved_at: str) -> ScrapeResult [raises: _UnparseableResult]` | read top-level `markdown` and `metadata.sourceURL` |
| `_parse_batch_scrape_result` **[A4]** | `(result: CallToolResult, retrieved_at: str) -> BatchScrapeResult \| str [raises: _UnparseableResult]` | read the batch envelope's `data[]` into `ScrapeResult`s, or return a job id to poll |
| `_log_attempt` **[A1, A2]** | `(tool: str, attempt: int, failure: ToolFailure, target: str \| None = None) -> None` | record one failed attempt as WARN |
| `create_mcp_tool_gateway` **[A3]** | `(settings: Settings) -> McpToolGateway` | composition root; opens nothing; passes probe URL |

**Module constants** **[A1, A2, M1, M2, R1]**: add map and scrape tool names, their argument tuples, `MAP_TIMEOUT_SECONDS`, `SCRAPE_TIMEOUT_SECONDS`, `FIRECRAWL_PROBE_URL_DEFAULT`; rename `CRAWL_CONCURRENCY` to `FIRECRAWL_CONCURRENCY`; remove `FIRECRAWL_CRAWL_ARGS` (no reader once the check drops crawl). Keep `FIRECRAWL_CRAWL_TOOL`, `FIRECRAWL_STATUS_TOOL`, `FIRECRAWL_STATUS_JOB_ARG` for the retained crawl path.

**Module constants (iteration 3)** **[A4, M8, M9, M10]**, with the agreed starting values:
- `BATCH_MAX_CONCURRENCY = 2` [A4, M9]; `BATCH_DEADLINE_SECONDS = 300.0`, `BATCH_POLL_INTERVAL_SECONDS = 5.0` [A4, M10]; batch-scrape / batch-status / batch-errors tool names and their job-id argument (names read from the authenticated `tools/list` at build time, OV-11).
- Retry backoff split by kind [M8]: keep `RETRY_BACKOFFS_SECONDS = (2.0, 3.0)` for `timeout`/`transport`; add `RATE_LIMIT_BACKOFFS_SECONDS = (30.0, 60.0)` used for `rate_limited`, overridden by a response `Retry-After` when present; 2 retries / 3 attempts retained.
- `FIRECRAWL_CONCURRENCY = 2` (plan browser limit) [M9]; `SEARCH_CONCURRENCY = 4` unchanged.
- `MAP_TIMEOUT_SECONDS = 60.0`, `SCRAPE_TIMEOUT_SECONDS = 60.0` (raised from 45/30), queue-inclusive [M10]; `SEARCH_TIMEOUT_SECONDS = 30.0`, `CRAWL_CALL_TIMEOUT_SECONDS = 60.0`, `CRAWL_DEADLINE_SECONDS = 180.0`, `CRAWL_POLL_INTERVAL_SECONDS = 3.0` kept.

These remain unmeasured starting values; the rate-window figure (OV-8) and the queue-inclusive budgets (OV-10) are confirmed on the runner, and the batch tool names at build time (OV-11).

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
| 6b | `batch_scrape`, `_read_batch_job` **[A4]** | list of page urls | `BatchScrapeResult` or `ToolFailure` | typed pages keyed by source URL, job totals, failed urls |
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

(urls)                                                          # batch_scrape  [A4]
 → arguments{ urls, formats=["markdown"], maxConcurrency=BATCH_MAX_CONCURRENCY }
 → [Firecrawl slot] → shared Client → call_tool(firecrawl batch scrape) under batch budget [M10]
 → start envelope → job id → _read_batch_job polls status, follows `next` cursor
 → data[] pages → BatchScrapeResult{ pages[ScrapeResult], total, completed, failed_urls }
 | unreadable envelope → ToolFailure(unparseable)
 | whole-job timeout/transport/rate_limited → ToolFailure(kind)   # per-URL misses ride failed_urls

(any Firecrawl call)                                            # classification  [M5, M6, M7]
 → httpx2.AsyncClient read timeout matches the call budget, not 5 s default   [M5]
 → MCPError(SSE-ended / reconnect-exhausted) → _classify_failure → transport  [M6]  → retried
 → 429 (bare status or wrapped in MCPError) → _classify_failure → rate_limited [M7] → retried
 → rate_limited retry waits a window-clearing backoff                          [M8]
```

**Approach at the real decision points:**
- Capability: Parallel needs `web_search(objective, search_queries)`; Firecrawl needs `firecrawl_map(url)` and `firecrawl_scrape(url, formats)`. Crawl and status tools are not checked. A miss raises `McpToolUnavailableError(stage="verify_capabilities")`.
- The probe runs only after the capability check passes, inside `open`'s teardown guard, so a probe failure closes both sessions before the exception leaves.
- Map and scrape retry on timeout, transport error and rate limit (2 s then 3 s). A non-rate-limit `is_error` makes one attempt. Exhaustion returns a `ToolFailure`.
- Only "cannot connect", "expected tool or argument missing" and "Firecrawl output shape not confirmed" raise. Everything else degrades per item (D5).
- The gateway never replaces a session or `Client` (D1). A timeout means our side stopped waiting; the session stays open. A dead session shows as repeated `ToolFailure(transport)` and is what V2a and V2b would reveal.
- **[M5, M6, M7, M8]** A Firecrawl call's SSE stream read is now bounded by the call budget, not httpx's 5 s default, so a slow-but-live stream is not severed early. A dropped stream (`MCPError`, SSE-ended / reconnection-exhausted) classifies as `transport` and a `429` classifies as `rate_limited`, both even when the SDK wraps them in `MCPError`; both are transient, so the shared retry path retries them on the same session (a retry reissues the call as a new request stream, not a replaced `Client`, keeping D1). A `rate_limited` retry waits a window-clearing backoff so it does not fall inside the same throttled minute.
- **[A4]** `batch_scrape` starts one job and reads it to completion by id, the same start-then-poll shape as `crawl_site`; per-URL failures inside a completed job ride `failed_urls`, not a whole-job `ToolFailure`. `scrape_page` stays for single-page use and the probe; C3.1.6 chooses which to use for Phase-2 fan-out.

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

**`_streamable_http_factory` [M5]**
- **Purpose:** build the caller-owned `httpx2.AsyncClient` and the `Client` with a read timeout that fits the call budget.
- **What it does:** construct `httpx2.AsyncClient(headers=…, timeout=…)` with an explicit timeout whose read bound is at least the longest per-call budget (map 45 s), rather than leaving httpx's 5 s default to sever a slow SSE response; the bearer header handling is unchanged. The per-call `asyncio.timeout` and SDK `read_timeout_seconds` still bound each call.
- **Failure:** unchanged; a connect failure still raises `McpConnectionError(stage="open")` through `_ServerSession`.

**`_classify_failure` [M6, M7]**
- **Purpose:** map an exception or an `is_error` result to a `ToolFailureKind` so the retry path and the caller react correctly.
- **What it does:** keep the existing branches (timeout, 429 by `status_code`/text, `_TRANSPORT_ERRORS`, else `tool_error`), and add: `mcp.shared.exceptions.MCPError` whose message is the SSE-ended / reconnection-exhausted disconnect classifies as `transport` [M6]; a `429` that the SDK surfaces inside an `MCPError` (not as a bare `status_code`) classifies as `rate_limited` [M7]. Order the checks so a 429-bearing `MCPError` is read as `rate_limited` before the generic SSE-ended `transport` branch.
- **Failure:** pure function; returns a kind, never raises. Whether the SDK buries the status in `MCPError` is OV-7; if it exposes `status_code==429`, M7 is already covered (check only).

**`batch_scrape` and `_read_batch_job` [A4]**
- **Purpose:** scrape many pages in one server-side-concurrent job instead of N single calls serialized by the Firecrawl pool.
- **What it does:** validate the URL list (non-empty; each a non-empty `http(s)` URL, same rule as `scrape_page`); take one Firecrawl slot; start the batch job with `formats=["markdown"]` and a per-job `maxConcurrency` within the plan limit; the start response is either inline pages or a job id. For a job id, `_read_batch_job` polls the batch-status tool by id under the batch deadline [M10], following the `next` cursor until no more pages. Parse each `data[]` element into a `ScrapeResult` keyed by its own `metadata.sourceURL`; record per-URL failures in `failed_urls` (from the batch error listing). Return `BatchScrapeResult`.
- **Failure:** bad input raises `ValueError`; session-not-open propagates `McpConnectionError`; a whole-job timeout/transport/rate-limited outcome returns `ToolFailure(kind)` after the shared retry; an unreadable envelope returns `ToolFailure(unparseable)`. A single page failing inside a completed job is **not** a whole-job failure; it rides `failed_urls`.

**`_streamable_http_factory` timeout [M5]**
- Build `httpx2.AsyncClient(timeout=httpx2.Timeout(connect=10.0, read=None, write=10.0, pool=10.0))`. `read=None` leaves the SSE stream unbounded at the transport; the per-call `asyncio.timeout` and SDK `read_timeout_seconds` are the single duration source. The bearer-header handling is unchanged.

**Retry backoff [M8] and Firecrawl concurrency [M9] and timeouts [M10]**
- **M8:** backoff is split by kind in `_call_with_retry`: `timeout`/`transport` use `RETRY_BACKOFFS_SECONDS = (2.0, 3.0)`; `rate_limited` honors a response `Retry-After` if present, else `RATE_LIMIT_BACKOFFS_SECONDS = (30.0, 60.0)`. Retry count stays 2 (3 attempts); the loop structure is unchanged. The per-minute window the 30/60 values target is OV-8.
- **M9:** `FIRECRAWL_CONCURRENCY = 2` (plan browser limit), surfaced at the composition root; A4's per-job `BATCH_MAX_CONCURRENCY = 2`. Jointly they can request up to 4 browsers only if a batch overlaps a single scrape; the excess queues (not a 429), and C3.1.6 avoids that overlap per amenity (OV-9). `SEARCH_CONCURRENCY = 4` unchanged.
- **M10:** `MAP_TIMEOUT_SECONDS = 60.0`, `SCRAPE_TIMEOUT_SECONDS = 60.0`, `BATCH_DEADLINE_SECONDS = 300.0` (poll 5 s) include Firecrawl's queue wait so a still-queued job is neither dropped early nor awaited long past Firecrawl's own timeout; `SEARCH_TIMEOUT_SECONDS = 30.0` and the retained crawl budgets are unchanged (OV-10).

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

### `_streamable_http_factory` [M5]
**Core behavior:** build the httpx2 client and the `Client` with a read timeout matched to the call budget.
**Drifts handled:**
- **Slow-but-live SSE stream severed by the default 5 s read timeout.** Observed in the live trace (map streamed >5 s → `httpx2.ReadTimeout`). Caught at **infra** (the client build). **Recovered** by setting an explicit `timeout` whose read bound is at least the longest per-call budget, so the call budget, not a transport default, bounds the stream.
**Left out (why):**
- A separate connect/read/write timeout per phase: one read bound tied to the budget is enough until a capture shows a distinct connect problem. *Imaginary.*
- Retrying the stream inside the factory: retry belongs to `_call_with_retry`, which now retries the `transport` kind (M6). *Wrong boundary.*

### `_classify_failure` [M6, M7]
**Core behavior:** map an exception or `is_error` result to a `ToolFailureKind`.
**Drifts handled:**
- **`MCPError` (SSE-ended / reconnection-exhausted) read as `tool_error`.** Grounded in the live trace. Caught in the **core** classifier. **Recovered** by classifying it `transport` so the shared retry reissues the call on the same session; a probe disconnect becomes `McpConnectionError(verify_probe)`.
- **`429` buried inside an `MCPError` rather than a bare `status_code`.** Caught in the **core** classifier. **Recovered** by matching the 429 inside the `MCPError` and returning `rate_limited`, ordered before the generic SSE-ended branch. Whether the SDK buries it is OV-7.
**Left out (why):**
- Parsing arbitrary `MCPError` subtypes into fine-grained kinds: only the SSE-ended and 429 cases are observed; others stay `tool_error`. *Not live.*
- Treating every `MCPError` as transport: a genuine tool error wrapped as `MCPError` must not be retried forever; only the SSE-ended/reconnect message is transport. *Trust (de-mask on the message, not the type alone).*

### `batch_scrape` and `_read_batch_job` [A4]
**Core behavior:** start one batch job over many URLs, poll by id, return typed pages.
**Drifts handled:**
- **Bad input.** Empty list, or a non-`http(s)` / empty URL in it. Caught at the method **edge**. **Rejected** with `ValueError`, matching `scrape_page`.
- **Session not open.** Caught in the core via `client()`. **Propagated** as `McpConnectionError`.
- **Start/poll call fails, times out, or is rate limited.** Shared call path. **Recovered** by retry (M8), then returned as a whole-job `ToolFailure`. The start call is never silently re-issued after a timeout (a batch job may already be billed), matching the `crawl_site` rule.
- **Paginated results.** The job returns pages across a `next` cursor. Caught in `_read_batch_job`. **Recovered** by following the cursor to the end before building the result, so pages are not silently truncated.
- **Per-URL partial failure inside a completed job.** Some URLs fail while the job completes. Caught in the parser via the batch error listing. **Recovered (degrade, signaled):** the failed URLs ride `failed_urls`; the job is not turned into a whole-job failure, and the degrade is visible in the result and a WARN log.
- **Unreadable job envelope.** `_parse_batch_scrape_result`. **Rejected** as `ToolFailure(unparseable)`, never a confident empty page set (de-mask).
- **Deadline.** A job that never completes within the batch deadline. Caught in `_read_batch_job`. **Rejected** as `ToolFailure(timeout)` carrying the job id, matching the crawl deadline rule.
**Left out (why):**
- Splitting a large URL list into sub-batches, or a per-URL retry: C3.1.6 owns fan-out shaping and the call cap. *Wrong boundary.*
- Host-filtering or de-duping the URL list: C3.1.6 owns candidate shaping. *Wrong boundary.*
- Tolerating a non-3.x per-page shape: the connect-time probe already fails older shapes. *Trust (probe).*
- Tolerating the batch tool being absent: its existence is confirmed by the domain owner; the exact name is read from `tools/list` at build time (OV-11). *Trust (confirmed).*
- Capability-checking batch at connect: by user decision batch stays out of `verify_capabilities`; a missing/renamed batch tool surfaces as a per-call `ToolFailure` on first use, like `crawl_site`. *Not live (connect check scope).*

---

## H. Logging

Per the diagnostic-logger skill: one stream of structured lines, boundary crossings, silent drifts and state changes only; nothing narrates success. All lines use `DEEP_SEARCH_LOGGER_NAME` and are JSON, as the existing `mcp.*` events are.

| Event | Level | Node type | Fields | When |
| --- | --- | --- | --- | --- |
| `mcp.session_opened` | INFO | boundary | `server`, `authenticated` | per server at open (unchanged) |
| `mcp.probe_passed` **[A3]** | INFO | boundary | `map_link_count`, `scrape_chars`, `scrape_url_matches_probe` | once per `open` after both probe calls are typed |
| `mcp.call_attempt_failed` **[A1, A2]** | WARN (was INFO) | silent drift (recover) | `tool`, `attempt`, `kind`, `message`, `target` (map and scrape) | each failed attempt, retried or final |
| `mcp.map_links_skipped` **[A1]** | WARN | silent drift (degrade) | `url`, `skipped`, `kept` | only when entries were skipped |
| `mcp.batch_pages_failed` **[A4]** | WARN | silent drift (degrade) | `total`, `completed`, `failed` | only when a completed batch job has per-URL failures |
| `mcp.probe_passed` scrape disconnect note **[M6]** | WARN | silent drift (recover) | `tool`, `attempt`, `kind="transport"` | each retried SSE-ended attempt, via the existing `mcp.call_attempt_failed` line (kind now `transport`, not `tool_error`) |

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
| STAGE 4b, `batch_scrape` **[A4]** | several mapped pages in one job: per-page `url`/length, `total`/`completed`, `failed_urls`, or `ToolFailure` |
| STAGE 5, `crawl_site` (only with `--crawl`) | page count, job id, or `ToolFailure` |
| STAGE 6, `aclose` | owner tasks ended, second `aclose` is a no-op |

**Diagnostics (iteration 3, already in the runner).** A `--trace-calls` flag installs three redacted, sample-run-only tracers added while diagnosing the probe failure: `mcp_diag.call_tool_raised` / `mcp_diag.call_tool_is_error` (raw per-call outcome), `mcp_diag.transport` (the SDK transport logs, which exposed the `httpx2.ReadTimeout` and the `405` SSE-resume), and `mcp_diag.http_request` (request `Last-Event-ID` / `Mcp-Session-Id`). They edit no production code and stay off by default. Keep them; they are the instrument that confirms M5-M7 on the next live run.

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
| Slow stream vs timeout **[M5]** | a Firecrawl handler that streams for longer than the old 5 s default still completes, because the client timeout matches the call budget; proven with the in-process server delaying past 5 s |
| MCPError classification **[M6]** | `call_tool` raising `MCPError`(SSE-ended) is classified `transport`, retried (2+ attempts, same `Client`), then `ToolFailure(transport)` if persistent; a probe disconnect raises `McpConnectionError(verify_probe)` |
| 429-in-MCPError **[M7]** | a `429` surfaced inside an `MCPError` is classified `rate_limited` and retried; a bare `status_code==429` still is (check-only case kept) |
| Rate-limit backoff **[M8]** | a rate-limited call records the new window-clearing wait values, not `[2.0, 3.0]` |
| Firecrawl concurrency **[M9]** | in-flight Firecrawl calls never exceed `FIRECRAWL_CONCURRENCY`; the value equals the configured plan browser limit |
| Queue-aware timeout **[M10]** | a handler that stays "queued" past the old budget but within the new one still returns; forced-timeout assertions use the new budgets |
| Batch typed **[A4]** | a multi-page batch envelope parses to `BatchScrapeResult` with one `ScrapeResult` per `data[]` keyed by `sourceURL`; `next`-paginated results are fully collected; a per-URL failure rides `failed_urls` and logs `mcp.batch_pages_failed`; an unreadable envelope gives `ToolFailure(unparseable)`; a never-completing job gives `ToolFailure(timeout)` carrying the job id; bad input raises `ValueError` before any call |
| Session scope, secrets | unchanged; the key-hygiene case also runs a map, a scrape and a batch |

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
| Explicit httpx2 client timeout matched to the call budget [M5] | the live map call streamed for >5 s and httpx's 5 s default severed it | every map/scrape/batch slower than 5 s fails at connect-probe and mid-run |
| `MCPError`(SSE-ended) classified `transport`; 429-in-`MCPError` classified `rate_limited` [M6, M7] | the disconnect and rate limits must retry, not abort as a misleading "wrong shape" | a dropped stream or a throttle ends the run at the probe instead of retrying |
| Window-clearing rate-limit backoff [M8] | a 429 retry must wait past the per-minute window | both retries fall inside the same throttled minute and waste the attempt |
| `FIRECRAWL_CONCURRENCY` sized to the plan browser limit [M9] | over-submitting self-induces 429 under the 2-browser limit | the gateway throttles itself and loses throughput, or trips the vendor limit |
| `batch_scrape` as a typed Protocol member returning `BatchScrapeResult` [A4] | a site scrape touches several pages; N single calls serialize on the 2-browser pool | Phase-2 scraping is N serialized round trips instead of one job |
| `BatchScrapeResult` reuses `ScrapeResult` per page | callers already key evidence by `ScrapeResult.url` | a second per-page type forces callers to handle two page shapes |

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
| A new `ToolFailure` kind for a dropped stream (M6) | rejected | the SSE-ended disconnect is a `transport` fault; the existing kind carries the reaction |
| A per-page `BatchPage` type distinct from `ScrapeResult` (A4) | rejected | the page shape is identical; one wrapper plus the existing type is enough |
| A separate semaphore pool for batch vs single scrape (A4, M9) | rejected | all Firecrawl calls share one plan-sized pool; per-job `maxConcurrency` bounds server-side fan-out |
| Reconnecting/replacing the session on an SSE disconnect (M6) | rejected | a `transport` retry reissues the call on the same `Client`; D1 (no replacement) stands |
| A retry library for the longer backoff (M8) | rejected | the existing `_call_with_retry` loop plus new constant values suffices |
| Splitting a large URL list into sub-batches in the gateway (A4) | rejected | C3.1.6 owns fan-out and the call cap; the gateway runs one job per call |

**Over-engineering guard: every element retained in this iteration and its one-line justification**

| Element | One-line justification |
| --- | --- |
| `ToolGateway` Protocol members `map_site`, `scrape_page` | callers depend on typed operations, not MCP content blocks |
| `MapLink`, `MapResult`, `ScrapeResult` | spec requires typed results; callers key by URL and need fixed fields |
| `FIRECRAWL_PROBE_URL` setting | the probe target must be changeable without a code edit and no amenity URL exists at `open` |
| `target` field in the failure log | ties a failed attempt to its page, since gateway lines carry no other page identity |
| `MAP_TIMEOUT_SECONDS`, `SCRAPE_TIMEOUT_SECONDS` | spec requires scrape's own timeout; map is bounded the same way |
| explicit httpx2 client `timeout` [M5] | the httpx 5 s read default severed a live map stream; the budget must bound the stream |
| `MCPError`/429 branches in `_classify_failure` [M6, M7] | a dropped stream and a throttle must retry, not end the run as "wrong shape" |
| window-clearing `rate_limited` backoff [M8] | a short retry inside the throttled minute is wasted; the wait must clear the window |
| `FIRECRAWL_CONCURRENCY` = plan browser limit [M9] | the cap stops the gateway self-inducing 429 under the 2-browser limit |
| `batch_scrape` + `BatchScrapeResult` + `_read_batch_job` [A4] | one job scrapes many pages without serializing on the 2-browser pool; callers key by the existing `ScrapeResult.url` |

## Layer 3: Wiring

**E. Dependency Direction**
```
AmenitySearch → [ToolGateway] ← McpToolGateway → _ServerSession → mcp.Client → httpx2.AsyncClient
McpToolGateway → McpServerConfig, result types, McpGatewayError
create_amenity_search → create_mcp_tool_gateway → Settings (keys, URLs, probe url)
```

**F. Composition Root**
- **Where:** `create_amenity_search(settings)` in `amenity_search.py`, which calls `create_mcp_tool_gateway(settings)` in `clients/mcp_tools.py`.
- **Selects:** keys, URLs and the probe URL from `Settings`; module-constant starting values (unmeasured, configurable). **Iteration 3 updates in bold:** search timeout 30 s, **map timeout 60 s (was 45)**, **scrape timeout 60 s (was 30)**, **batch deadline 300 s, batch poll 5 s**, crawl per-call 60 s, crawl overall deadline 180 s, crawl poll 3 s, transient retry waits 2 s then 3 s, **rate-limited retry waits `Retry-After` else 30 s then 60 s**, search semaphore 4, **Firecrawl semaphore 2 (= plan browser limit)**, **batch per-job maxConcurrency 2**, **httpx `Timeout(connect=10, read=None, write=10, pool=10)`**.
- **Lifecycle:** the factory opens nothing. `open()` runs at the start of `run_llm_metric_resolution` and `aclose()` at its end. `AmenitySearch.aclose()` also closes the gateway (covers a leaked session). Probe runs inside `open`.

**G. Async Execution Map** (placement set by blocking behavior, ordering by data dependency, decided separately)

| Operation group | Operations and I/O | Data dependency | Placement | Ordering | Shared-state handling | Blocking / worker |
| --- | --- | --- | --- | --- | --- | --- |
| Session open | HTTP connect, MCP handshake per server | independent | event loop, one owner task per server | concurrent (gather of the two ready signals) | each owner task writes only its own session | none; no worker |
| Capability check | `list_tools` per server | independent; needs open sessions | event loop | concurrent (gather) | read only | none; no worker |
| Firecrawl probe **[A3]** | `map_site` and `scrape_page` on the probe URL | independent of each other; needs verified capabilities | event loop | concurrent (gather, exceptions collected); probe starts after the check | each call returns a value; no shared writes | none; every call under `asyncio.timeout` and SDK read timeout |
| Search call path | semaphore wait, `call_tool`, backoff sleep | retry depends on previous attempt | event loop | sequential inside one call; calls from different amenities gathered by the caller (later) | per-server semaphore bounds in-flight; results returned | none; every call under timeout |
| Map and scrape call path **[A1, A2]** | semaphore wait, `call_tool`, backoff sleep | retry depends on previous attempt; map and scrape of different pages are independent | event loop | sequential inside one call; scrapes of different pages gathered by the caller (C3.1.6 Phase 2) | one Firecrawl pool (sized to the plan browser limit [M9]) bounds in-flight map, scrape, batch and crawl; results returned | none; every call under timeout (budget includes queue wait [M10]) |
| Batch scrape call path **[A4]** | semaphore wait, start `call_tool`, status polls by job id, `next`-cursor reads | each poll and each cursor read depends on the job id and the prior page | event loop | sequential inside one call; server-side page concurrency is set by the job's `maxConcurrency`, not the event loop | same Firecrawl pool [M9]; one slot per in-flight batch job | none; every call under the batch budget [M10] |
| Crawl call path | semaphore wait, start `call_tool`, status polls by job id | each poll depends on the job id | event loop | sequential inside one call | same pool as above | none; no worker |
| Result parsing | JSON decode, dataclass build | needs its own response | inline on event loop | sequential after the call | none | short CPU; revisit if a capture shows multi-megabyte map bodies |
| Close | signal and await owner tasks | independent | event loop | concurrent (gather) | each task exits its own contexts | none; no worker |

Owner tasks exist because the SDK client holds a task group (a set of child tasks) that the same task must enter and exit. All operations use the async-native `httpx2` client, so nothing is offloaded to a thread or process.

**H. End-to-End Flow**
1. A caller (later `run_llm_metric_resolution`) calls `tool_gateway.open()`.
2. Two owner tasks connect; `verify_capabilities` checks `web_search`, `firecrawl_map`, `firecrawl_scrape` with their arguments.
3. The probe maps and scrapes the probe URL together and confirms the 3.x JSON shape, or `open` closes both sessions and raises.
4. Callers (later pipelines) call `search_web`, `map_site`, `scrape_page` and `batch_scrape`, each bounded by its server's semaphore. `crawl_site` stays available but unused by M3.
5. Each call uses the server's shared client, runs under a queue-inclusive timeout [M10], and retries transient failures (now including an `MCPError` SSE disconnect [M6] and a 429 wrapped in `MCPError` [M7], with a window-clearing backoff [M8]) on the same session, returning a typed result or `ToolFailure`. The client's read timeout is matched to the call budget [M5], not httpx's 5 s default.
6. The caller ends with `aclose()`; `AmenitySearch.aclose()` repeats it harmlessly.

## Layer 4: Backing

- **Owner task per server:** the locked same-task scope cannot be met from arbitrary tasks because of the SDK task group.
- **No session replacement:** a timeout stops our wait and does not break the session; V2a and V2b judge this, and a failure sends the shared-Client approach back for review, as locked. D1 confirmed this for iteration 2. Iteration 3 keeps it: an `MCPError` SSE disconnect now retries (M6) by reissuing the call as a new request stream on the same `Client`, not by replacing the session.
- **Transport read timeout matched to the budget [M5]:** the SSE response stream is read under the call budget, not httpx's 5 s default; the live trace showed the default severing a map that streamed for ~9 s.
- **Classifier owns the retry decision [M6, M7]:** a dropped stream and a 429 are transient and must retry; leaving `MCPError` as `tool_error` ended the run at the probe with a misleading "wrong shape".
- **One plan-sized Firecrawl pool [M9] and queue-aware budgets [M10]:** the single pool and the queue-inclusive timeouts keep the gateway inside the vendor's 2-browser / per-minute limits without dropping queued jobs.
- **Batch over N single calls [A4]:** one job is one submission and one job clock; `scrape_page` stays for single-page use and the probe.
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
| OV-7 | Does the MCP SDK expose a 429 as `status_code`/`response`, or bury it inside `MCPError`? [M7] | run the runner with `--trace-calls`; read the `mcp_diag.call_tool_raised` / `mcp_diag.transport` lines. Handled either way: M7 checks `status_code==429` **and** the rate-limit regex against `str(exc)` including inside `MCPError`, so classification holds regardless; this run only tells us whether the regex branch is actually exercised |
| OV-8 | Confirm the rate-limit backoff window [M8] | **Starting value set:** honor `Retry-After`, else `(30.0, 60.0)` for `rate_limited`. Residual: read Firecrawl's per-minute rate figure from its pricing/limits page and adjust if the window differs. Free per-minute number not in the provided text |
| OV-9 | `FIRECRAWL_CONCURRENCY` vs batch `maxConcurrency` [M9, A4] | **Resolved (structural):** `FIRECRAWL_CONCURRENCY = 2`, `BATCH_MAX_CONCURRENCY = 2`; C3.1.6 runs one batch or singles per amenity so they do not jointly exceed the plan. Residual: confirm Free = 2 browsers still holds on the account's plan |
| OV-10 | Confirm the queue-inclusive timeout values [M10] | **Starting values set:** map 60 s, scrape 60 s, batch deadline 300 s (poll 5 s). Residual: measure start-to-complete time (including queue wait) on the runner under the 2-browser limit and tighten so a queued job is neither dropped early nor awaited past Firecrawl's own timeout |
| OV-11 | Exact batch-scrape (and status/errors) MCP tool names and arguments on the authenticated session [A4] | **Existence confirmed by the domain owner** (the authenticated session exposes a batch tool). Residual: read the exact tool name and argument tuples from the authenticated `tools/list` at build time so the batch constants bind to the real name, not a guessed one. The authenticated session already lists more tools than keyless (keyless advertised only `firecrawl_search`/`firecrawl_scrape`/`firecrawl_parse`; authenticated adds `firecrawl_map`/`firecrawl_crawl`). |
| OV-12 | Vendor: does the MCP endpoint support GET-based SSE resume (it answered `405`)? [M6] | confirm with Firecrawl; M5/M6 make the gateway resilient regardless |

## Handoffs to later sub-components

| To | What the gateway guarantees or leaves to it |
| --- | --- |
| C3.1.3 | passes app-injected homepage URL to `map_site` and the id-resolved URL to `scrape_page`; the gateway does no host check |
| C3.1.4 | empty `links` and empty `text` arrive as valid results, never failures; timeouts and parse misses arrive as `ToolFailure` |
| C3.1.6 | applies the 50-candidate cap, URL dedup and fan-out; keys evidence by the returned `ScrapeResult.url` (per Firecrawl's docs the requested URL; not live-verified); chooses `batch_scrape` (one job, many pages) over repeated `scrape_page` for Phase-2 multi-page scraping [A4], and keeps the URL list within the plan limit alongside the gateway's own cap [M9] |
| C3.1.6/C3.1.7 | owns the per-amenity correlation id for log lines; counts gateway-internal retries when it reasons about call caps |

---

# Appendix: C3.1.1 Iteration Report: built spec -> "Fixes to be incorporated in iteration"

This is the stage-one report (per `skills/iteration_report.md`) that this iteration-3 plan implements. It
replaces the earlier iteration-1->2 report. The point IDs below are renumbered to continue this plan's
existing ID space so they do not collide with iteration-2's A1-A3 / M1-M4 / R1: **A4** = batch_scrape,
**M5-M10** = the five transport/limit fixes plus the new op's timeouts, flags **F15+**.

**How to read the traceflows:** each one is a top-down tree, and the status tag sits in one aligned
column at the right of each diagram. `◄── NEW` = added, `◄── CHANGED` = altered, `◄── GONE` = removed.
BEFORE and AFTER are stacked, each scoped to its own point.

---

## Report 1. Confirmation

- **Read, in full:** the skill (`skills/iteration_report.md`); the **old spec** = C3.1.1 as currently
  written (`deep_search_context.md` L2778-2808); the **old implementation plan** (this file, iteration 2);
  the **new requirements** = the "Fixes to be incorporated in iteration" section (`deep_search_context.md`
  L2810-2825).
- **"Implemented" means** old spec + plan, including the build-time corrections carried forward: one owner
  task per server; **no session replacement / no reconnect** (D1); **`httpx2.AsyncClient`** as the
  caller-owned client (D2); unrecognised bodies de-masked to `ToolFailure(unparseable)`; `open()` tears down
  on any non-local exit; `ValueError` on bad input.
- **Artifact names** come from the plan's file table (`#2` config.py, `#3` .env.example, `#4`
  exceptions/mcp.py, `#5` clients/mcp_tools.py, `#9` tests/.../test_mcp_tool_gateway.py, `#10`
  mcp_tool_gateway_sample_run.py, `#11` deep_search_context.md, `#12` feature_tests test, `#13` test-plan
  doc) and its symbol blueprint. Symbols the plan names (`_streamable_http_factory`, `_classify_failure`,
  `_call_with_retry`, `_read_crawl_job`, `FIRECRAWL_CONCURRENCY`, `MAP_TIMEOUT_SECONDS`,
  `SCRAPE_TIMEOUT_SECONDS`, `ScrapeResult`, `ToolGateway`) are used as-is; ones in code but not named in the
  plan are `(illustrative)`. A change the fixes imply but do not state is `(inferred)`.
- **Repo context gathered this session:** the live failure trace that motivated the fixes and the confirmed
  httpx default read timeout of 5.0 s.
- **Result:** **1 ADD (A4), 6 MODIFY (M5-M10), 0 REMOVE, 0 DECISION-GATED**, plus Unchanged and flags
  F15-F23. Fix 6 (vendor-confirm the `405` on GET resumption) carries **no code artifact** and is recorded
  in Flags (F15) and OV-12, not as an implementation point.
- **No DECISION-GATED points:** each fix was checked against D1 (no session replacement) and D2 (`httpx2`);
  none contradicts them. M6's retry reissues a call on the same session (a new request stream), not a
  replaced `Client`, so D1 holds; M5 keeps `httpx2`.

---

## Report 2. Current traceflow, with change locations

```
run_llm_metric_resolution                               (C3.1.7, not built yet)
│
└─ McpToolGateway                                        (mcp_tools.py, #5)
   │
   ├─ open()
   │    └─ start sessions ─ _streamable_http_factory          ◄── M5
   │          httpx2.AsyncClient(headers)  no timeout → 5 s    ◄── M5
   │
   ├─ shared call path ─ _call_with_retry / _single_call
   │    ├─ call_tool ──► CallToolResult | raises
   │    ├─ _classify_failure(exc | result)                     ◄── M6, M7
   │    │     MCPError(SSE-ended) ──► tool_error  (not retried) ◄── M6
   │    │     429 wrapped in MCPError ──► tool_error            ◄── M7
   │    └─ backoff (2 s, 3 s)                                   ◄── M8
   │
   ├─ Firecrawl slot pool  FIRECRAWL_CONCURRENCY = 2           ◄── M9
   │
   ├─ map_site / scrape_page   MAP=45 s / SCRAPE=30 s timeouts ◄── M10
   ├─ scrape_page(url)         one page                        (kept; A4 is multi-page)
   ├─ batch_scrape(urls)       attaches here                   ◄── A4
   │
   └─ aclose()
```

Also touched outside this flow: the `ToolGateway` Protocol gains `batch_scrape` (A4); `RETRY_BACKOFFS_SECONDS`
(M8), `FIRECRAWL_CONCURRENCY` (M9) and the timeout constants (M10) are composition-root values; `_read_crawl_job`
is the poll pattern A4 mirrors; the vendor `405` resumption is a verification item (F15 / OV-12).

| ID | Class | Summary |
|----|-------|---------|
| A4 | ADD | `batch_scrape(urls)` over Firecrawl batch scrape + its job envelope → typed results |
| M5 | MODIFY | Explicit read timeout on the httpx2 client in `_streamable_http_factory` (was default 5 s) |
| M6 | MODIFY | `_classify_failure` maps `MCPError` (SSE-ended / reconnect-exhausted) → `transport` |
| M7 | MODIFY | `_classify_failure` reaches `rate_limited` for a `429` even when wrapped in `MCPError` |
| M8 | MODIFY | Retry backoff lengthened to clear a per-minute rate window (`RETRY_BACKOFFS_SECONDS`) |
| M9 | MODIFY | Cap gateway submission concurrency to the vendor plan limit (`FIRECRAWL_CONCURRENCY`) |
| M10 | MODIFY | Per-call timeouts account for Firecrawl's queue-inclusive job clock |

---

## Report 3. ADD points

### A4: `batch_scrape(urls)` over Firecrawl batch scrape

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `ToolGateway` Protocol | add: a `batch_scrape(urls, formats=["markdown"])` member returning typed per-page results or a `ToolFailure`, so callers and the fake see one batched scrape with no MCP types. |
| mcp_tools.py (#5) · `McpToolGateway.batch_scrape` (illustrative) | add: start a batch job over a URL list and read it to completion by job id, mirroring the retained `crawl_site` / `_read_crawl_job` start-then-poll pattern; set the per-job `maxConcurrency` within the plan limit (ties to M9). |
| mcp_tools.py (#5) · `BatchScrapeResult` wrapper (illustrative) | add: a job-level wrapper (pages, total, completed, failed_urls, retrieved_at) holding a list of the existing `ScrapeResult`; reuse `ScrapeResult`, do not invent a per-page type. |
| mcp_tools.py (#5) · `_parse_batch_scrape_result`, `_read_batch_job` (illustrative) | add: iterate the job envelope's `data` array, key each page by its own `metadata.sourceURL`, tolerate per-URL partial failures, follow the `next` cursor; unreadable envelope → `ToolFailure(unparseable)`. |
| mcp_tools.py (#5) · batch tool-name constants (illustrative) | add: the batch-scrape / batch-status / batch-errors MCP tool names and argument tuples beside the `FIRECRAWL_*` constants. **Existence confirmed by the domain owner; the exact names/args are read from the authenticated `tools/list` at build time — F21 / OV-11.** |
| test_mcp_tool_gateway.py (#9), feature_tests test (#12) | add: in-process batch fixtures (multi-page `data`, partial per-URL failure, paginated `next`, empty, unparseable, never-completing) plus start+poll, retry and timeout cases. |
| mcp_tool_gateway_sample_run.py (#10) | add: STAGE 4b that batch-scrapes the mapped pages and prints per-page url/length and the job totals. |
| deep_search_context.md (#11) | modify: add `batch_scrape` and its envelope parse rule to the C3.1.1 operations text. |

BEFORE
```
McpToolGateway
├─ map_site(url)
├─ scrape_page(url)          one page per call, serialized by the pool
├─ crawl_site(...)           kept, unused by M3
└─ aclose()
```

AFTER
```
McpToolGateway
├─ map_site(url)
├─ scrape_page(url)                              kept (single page)
├─ batch_scrape(urls)                                        ◄── NEW
│    ├─ start batch job over the URL list                    ◄── NEW
│    ├─ poll by job id (mirrors _read_crawl_job)             ◄── NEW
│    └─ read job envelope                                    ◄── NEW
│         ├─ data[] → list[ScrapeResult], keyed by sourceURL ◄── NEW
│         ├─ follow `next` cursor for all pages              ◄── NEW
│         ├─ per-URL partial failure → failed_urls           ◄── NEW
│         └─ unreadable envelope ──► ToolFailure(unparseable)◄── NEW
└─ aclose()
```

Behaviour change: callers scrape many pages in one server-side-concurrent job instead of N single calls
serialized against the 2-browser limit, getting one result set keyed by source URL.

---

## Report 4. MODIFY points

### M5: Explicit read timeout on the httpx2 client

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `_streamable_http_factory` (named, D2 block) | modify: build `httpx2.AsyncClient(headers=…, timeout=…)` with an explicit read timeout matched to the call budget instead of httpx's default 5.0 s, which severs any SSE response slower than 5 s. |
| config.py (#2) / .env.example (#3) | check only (inferred): the timeout may be a module constant rather than a setting. |
| test files (#9, #12) | add: a case proving a response slower than the old 5 s default still completes. |

BEFORE
```
_streamable_http_factory
└─ httpx2.AsyncClient(headers)             no timeout → 5 s read default
     └─ slow SSE response (>5 s)  ──► httpx2.ReadTimeout ──► stream ends
```

AFTER
```
_streamable_http_factory
└─ httpx2.AsyncClient(headers, timeout=…)                 ◄── CHANGED
     └─ slow SSE response (>5 s)  ──► read to completion       ◄── CHANGED
```

Behaviour change: a Firecrawl call whose result takes longer than 5 s to stream no longer dies on a
premature read timeout.

### M6: `_classify_failure` maps `MCPError` (SSE-ended) → `transport`

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `_classify_failure` (named) | modify: recognise `mcp.shared.exceptions.MCPError` for the SSE-ended / reconnection-exhausted case and return `transport` instead of `tool_error`, so it retries and is labelled honestly. |
| mcp_tools.py (#5) · `_TRANSPORT_ERRORS` (named, D2 block) | modify (inferred): add an explicit `MCPError` branch keyed on the disconnect message (not the type alone). |
| mcp_tools.py (#5) · `_probe_firecrawl_shape` | check only: a probe disconnect becomes a transient `McpConnectionError(verify_probe)` rather than `McpToolUnavailableError`. |
| test files (#9, #12) | add: `call_tool` raises `MCPError(SSE-ended)` → `ToolFailure(transport)`, retried. |

BEFORE
```
_single_call
└─ call_tool raises MCPError(SSE-ended)
     └─ _classify_failure ──► tool_error
          ├─ not in retry set ──► no retry
          └─ probe ──► McpToolUnavailableError(verify_probe) "wrong shape"
```

AFTER
```
_single_call
└─ call_tool raises MCPError(SSE-ended)
     └─ _classify_failure ──► transport                      ◄── CHANGED
          ├─ in retry set ──► retried on the same session    ◄── CHANGED
          └─ exhausted ──► ToolFailure(transport) | probe: McpConnectionError ◄── CHANGED
```

Behaviour change: a dropped stream is retried on the same session and, if persistent, surfaces honestly as
`transport`, not as a misleading "did not return the expected shape."

### M7: `429` reaches `rate_limited` even when wrapped in `MCPError`

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `_classify_failure` (named) | modify: classify a `429` (per-minute rate limit or exceeding max queued jobs) as `rate_limited` even when the SDK surfaces it inside an `MCPError`. **Whether the SDK buries the status is unverified — F17 / OV-7;** if it exposes `status_code==429`, the existing branch covers it (check only). |
| test files (#9, #12) | add: a `429`-bearing `MCPError` → `ToolFailure(rate_limited)`. |

BEFORE
```
_classify_failure(exc)
├─ status_code == 429           ──► rate_limited
├─ text matches rate-limit RE   ──► rate_limited
└─ MCPError hiding a 429        ──► tool_error   (missed)
```

AFTER
```
_classify_failure(exc)
├─ status_code == 429           ──► rate_limited
├─ text matches rate-limit RE   ──► rate_limited
└─ MCPError exposing a 429      ──► rate_limited              ◄── CHANGED
```

Behaviour change: rate-limit rejections are retried as rate limits rather than dropped as generic tool
errors.

### M8: Lengthen retry backoff to clear a per-minute rate window

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `RETRY_BACKOFFS_SECONDS` (illustrative; plan: "waits 2 s then 3 s") | modify: raise the `rate_limited` backoff so a retry waits past Firecrawl's per-minute window. **The concrete value is unspecified — F18 / OV-8.** |
| mcp_tools.py (#5) · `_call_with_retry` (named) | check only: the retry loop structure is unchanged; only wait values (possibly a per-kind wait) change. |
| test files (#9, #12) · retry cases | modify: the recorded-sleep assertions (`[2.0, 3.0]`) update to the new values. |

BEFORE
```
_call_with_retry (rate_limited)
└─ backoff ──► 2 s, then 3 s         retries likely inside the same minute
```

AFTER
```
_call_with_retry (rate_limited)
└─ backoff ──► longer, window-clearing waits   ◄── CHANGED
```

Behaviour change: a throttled call waits out the rate window before retrying.

### M9: Cap submission concurrency to the vendor plan limit

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `FIRECRAWL_CONCURRENCY` (named) | modify: size the single Firecrawl slot pool to the plan's concurrent-browser limit (Free = 2) so the gateway does not self-induce `429`s; make the rationale explicit (value may stay 2). Interacts with A4's server-side `maxConcurrency` — F19 / OV-9. |
| mcp_tools.py (#5) · `create_mcp_tool_gateway` (named) / config.py (#2) | check only (inferred): whether the cap becomes a plan-keyed setting or stays a constant. |
| test files (#9, #12) · concurrency case | check only: "in-flight never exceeds the pool" still holds at the chosen value. |

BEFORE
```
Firecrawl slot pool  FIRECRAWL_CONCURRENCY = 2    sized for crawl, re-check pending
```

AFTER
```
Firecrawl slot pool  FIRECRAWL_CONCURRENCY = plan browser limit   ◄── CHANGED
     └─ submission never exceeds the vendor concurrency ──► fewer self-induced 429s
```

Behaviour change: the gateway holds its own in-flight Firecrawl calls at or below the plan's browser limit.

### M10: Per-call timeouts account for Firecrawl's queue-inclusive job clock

| Artifact | Change |
|---|---|
| mcp_tools.py (#5) · `MAP_TIMEOUT_SECONDS`, `SCRAPE_TIMEOUT_SECONDS` (named), the crawl deadline and the new batch deadline (illustrative) | modify: choose timeouts that allow for queue wait under the 2-browser limit (Firecrawl's one clock runs submission→execution), so a still-queued job is neither dropped too early nor orphaned long after Firecrawl's own timeout. **No concrete value is given — F20 / OV-10.** |
| mcp_tools.py (#5) · `_streamable_http_factory` timeout (M5) | check only: the httpx read timeout (M5) and these budgets are chosen together. |
| test files (#9, #12) · timeout cases | modify: forced-timeout assertions update to the new budgets. |

BEFORE
```
map_site / scrape_page
└─ asyncio.timeout(MAP=45 / SCRAPE=30)   assumes execution time only
     └─ queued job still counts against Firecrawl's clock (unaccounted)
```

AFTER
```
map_site / scrape_page
└─ timeout chosen for submission + queue wait   ◄── CHANGED
     └─ queued-but-not-dropped, bounded against Firecrawl's own timeout  ◄── CHANGED
```

Behaviour change: a job waiting in Firecrawl's queue is given time to run rather than being timed out as if
it had already started.

---

## Report 5. REMOVE points

None. No built requirement or check is dropped by these fixes.

---

## Report 6. DECISION-GATED points

None. The fixes do not contradict the build-time corrections:
- **D1 (no session replacement):** M6's retry reissues a call on the same session (a fresh request/response
  stream), not a replaced `Client`.
- **D2 (`httpx2`):** M5 keeps `httpx2.AsyncClient` and only sets its `timeout`.

---

## Report 7. Unchanged

- `search_web`, `map_site`, `scrape_page`, `crawl_site` operations and their parsers (A4 adds a sibling; it
  does not change these).
- `_probe_firecrawl_shape`, `verify_capabilities`, the capability set, and `open()` teardown — unchanged in
  structure (M6 only changes how a probe-call disconnect is classified).
- Typed results / returned `ToolFailure`; failures returned not raised; keys never logged.
- Owner task per server; one shared `Client` per server; session scope; `aclose` idempotence.
- Error typing `McpConnectionError` / `McpToolUnavailableError` with `stage`.
- `ScrapeResult`, `MapResult`, `MapLink` contracts (A4 reuses `ScrapeResult`).
- V2a; `AmenitySearch` injection (#6); the `tool_gateway=None` callers (#7, #8); `requirements.txt` (#1).

---

## Report 8. Component traceflow after all points

```
run_llm_metric_resolution                               (C3.1.7)
│
└─ McpToolGateway                                        (mcp_tools.py, #5)
   │
   ├─ open()
   │    └─ start sessions ─ _streamable_http_factory(timeout set)   ◄── M5
   │
   ├─ shared call path ─ _call_with_retry / _single_call
   │    ├─ _classify_failure
   │    │     MCPError(SSE-ended)        ──► transport             ◄── M6
   │    │     429 (even inside MCPError) ──► rate_limited          ◄── M7
   │    └─ backoff = window-clearing waits                         ◄── M8
   │
   ├─ Firecrawl pool  FIRECRAWL_CONCURRENCY = plan limit           ◄── M9
   │
   ├─ map_site / scrape_page  timeouts incl. queue wait            ◄── M10
   ├─ scrape_page(url)        single page                          (kept)
   ├─ batch_scrape(urls)      job envelope ──► list[ScrapeResult]  ◄── A4
   │
   └─ aclose()

Open / vendor:
   F15 / OV-12  405 on GET SSE resumption — confirm with Firecrawl (no code)
```

---

## Report 9. Flags

| #   | Flag |
|-----|------|
| F15 | **Fix 6 is verification-only, no code artifact.** The `405 Method Not Allowed` on the SDK's GET SSE resume is a vendor behaviour to confirm (OV-12); M5/M6 make the gateway resilient regardless. |
| F16 | **M5 timeout value is open (OV-10).** Fix 1 offers "align to per-call budgets, or `None` for the stream" with no single value; M5 and M10 are chosen together. |
| F17 | **M7 may be change-or-check-only (OV-7).** If `429` arrives as `status_code`, the existing branch classifies it (check only); if buried in `MCPError`, M7 is a real change. Unverified — the same SDK opacity that masked the disconnect this session. |
| F18 | **M8 backoff length undefined (OV-8).** The Free-plan per-minute rate number is not in the provided text; the window-clearing wait has no concrete value yet. |
| F19 | **M9 ↔ A4 interaction (OV-9).** The gateway pool cap (M9) bounds single-call concurrency; batch (A4) pushes concurrency server-side via `maxConcurrency`. The two must be reconciled so they do not jointly exceed the plan. |
| F20 | **M10 value undefined, and a tension (OV-10).** Firecrawl's clock includes queue wait (hard ceiling 48 h); "account for queue time" conflicts with "fail fast." No concrete budget yet. |
| F21 | **A4 binds to a batch MCP tool whose exact name is read at build time (OV-11).** The authenticated session exposes a batch tool (confirmed by the domain owner); the batch-scrape / status / errors tool names and args are read from the authenticated `tools/list` so the constants are not guessed. Decided: batch is **not** capability-checked at connect (user decision), so `verify_capabilities` is unchanged (`web_search` + `firecrawl_map` + `firecrawl_scrape`); a missing or renamed batch tool surfaces as a per-call `ToolFailure` on the first `batch_scrape`, the same as the retained `crawl_site`. |
| F22 | **`scrape_page` vs `batch_scrape` ownership (handoff).** Fix 5 says batch "instead of many single `scrape_page` calls," but `scrape_page` (single page, and the probe) is retained. Which operation C3.1.6 fan-out uses for multi-page scraping is a handoff, not settled here. |
| F23 | **M6 retry semantics (inferred).** A retried call after `MCPError(SSE-ended)` opens a new request/response stream on the same `Client`; this assumes the dead SSE was per-request, not a dead session, keeping D1 intact. Worth confirming against the SDK. |

---

## Report self-check (against the skill's "Before answering")

- Every fix is in exactly one point or Unchanged: batch op + its parsing/paging/partial-failure (A4),
  httpx timeout (M5), MCPError classification (M6), 429-in-MCPError (M7), backoff (M8), concurrency cap (M9),
  queue-aware timeouts (M10); Fix 6 is F15 / OV-12 (no code). Everything else is in Report 7.
- Every old-spec requirement touched by a fix is in MODIFY; nothing is removed.
- Every artifact comes from the plan or is labelled `(illustrative)` / `(inferred)`.
- Every point has BEFORE/AFTER and a Behaviour-change line; no code, no implementation steps.
- IDs continue the plan's existing space (A4; M5-M10; F15+), stable for follow-ups.
