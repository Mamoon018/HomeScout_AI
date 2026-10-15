# Implementation Plan: Deep Search R2, Mechanism 3, C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl), Iteration 3 (extended by Iteration 4 — see the Iteration 4 appendix at the end)

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

**Iteration 4 change points (added after iteration 3, now in the code — verified against `mcp_tools.py`).** Full detail is in the **Iteration 4 appendix** at the end of this file; the iteration-3 body below is kept as built for provenance and is annotated where iteration 4 superseded it.

| ID | Class | Summary |
| --- | --- | --- |
| A5 | ADD | Resolve the batch-scrape / batch-status tool **names and job-id/cursor args from the live `tools/list`** at connect (`ResolvedBatchTools`, `_resolve_firecrawl_batch_tools`, `_match_batch_tool`, candidate constants); closes OV-11 |
| M11 | MODIFY | `verify_capabilities` now **requires and resolves** the batch tools at connect (reverses iteration-2/3's "batch stays out of the capability check"); unresolved → `McpToolUnavailableError(verify_capabilities)` |
| A6 | ADD | Connect/resolution diagnostics: `mcp.tools_listed`, `mcp.batch_tools_resolved`, `mcp.batch_arg_unresolved`, `mcp.batch_resolution_failed`, `mcp.batch_pages_truncated` |
| M12 | MODIFY | Sample runner: `--batch-only` (connect+verify, probe skipped, batch call only), `--trace-transport` (full relay), and `--trace-calls` scoped to the batch tools |

> **Iteration 4 is superseded by Iteration 5 (below).** A live `--batch-only` run proved the hosted `/v2` server lists **no batch tool** (28 tools, none containing `batch`), so A5/M11 cannot resolve anything on this endpoint. Iteration 5 is the response and is the **active plan to build next**.

**Iteration 5 change points (the active plan — executes the appended C3.1.1 Iteration Report).** Full detail is in the **Iteration 5 appendix** at the end of this file (skill artifacts) and the appended iteration report (point-by-point changes + updated spec). The iteration-3/4 body below is kept for provenance and annotated where iteration 5 supersedes it. Report-local IDs are renumbered into this plan's ID space to avoid colliding with the body's `M1`/`R1`.

| Plan ID | (report ID) | Class | Summary |
| --- | --- | --- | --- |
| M13 | (report M1) | MODIFY | Rename `batch_scrape`→`scrape_pages`, `BatchScrapeResult`→`ScrapeResults`; body becomes a concurrent `scrape_page` fan-out (`gather`, `return_exceptions=True`, per-URL misses ride `failed_urls`). No MCP batch tool exists on the endpoint |
| A7 | (report A7) | ADD | Proactive Firecrawl rate limiter: a per-minute token bucket (`FIRECRAWL_RATE_PER_MINUTE = 10`) acquired with `_firecrawl_sem` in `_single_call`, on **every** Firecrawl call (map/scrape/crawl); Parallel/`web_search` unaffected. Both gates are shared gateway state |
| R2 | (report R1) | REMOVE | Delete the batch job-envelope machinery: `_read_batch_job`, `_parse_batch_start`/`_parse_batch_status`, `BATCH_DEADLINE_SECONDS`/`BATCH_POLL_INTERVAL_SECONDS`/`BATCH_MAX_CONCURRENCY` |
| R3 | (report R2) | REMOVE | Revert iteration 4: delete `_resolve_firecrawl_batch_tools`, `_match_batch_tool`, `ResolvedBatchTools`, `FIRECRAWL_BATCH_*_CANDIDATES`/`_START_ARGS`, `_batch_identity`, the `verify_capabilities` batch branch, and the batch-specific A6 logs. Keep `mcp.tools_listed` |
| R4 | (report R3) | REMOVE | Delete the connect-time probe `_probe_firecrawl_shape` and its `open()` call (a live run confirmed the 3.x shape). Keep `FIRECRAWL_PROBE_URL` + `_decode_body`/`_parse_*` |

**Status tags used below.** `[ADD]`, `[MODIFY]`, `[REMOVE]` carry the iteration-report ID (iteration 5: A7, M13, R2, R3, R4). Untagged items are built and unchanged.

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
| **Iteration 5 cross-mechanism scan (M13 rename, R2/R3/R4 removals, A7)** | grep-verified: `batch_scrape` / `BatchScrapeResult` / `_probe_firecrawl_shape` appear only in `clients/mcp_tools.py`, the sample runner, the two gateway test files, and the C3.1.1 docs. No already-built mechanism calls them. | No other-mechanism code change needed. `amenity_search.py` (#6) still only injects the gateway and calls `aclose()` — unaffected by the rename. The Phase-2 caller that will call `scrape_pages` is **C3.1.6 (not yet built)** — a handoff, not an edit. Only the C3.1.1 docs (#11 spec body, #13 test plan) need the doc sync, already tracked. |
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
| 5 | `backend/src/clients/mcp_tools.py` | Modify | Result contracts, Protocol members, `map_site`, `scrape_page`, probe, capability set, semaphore rename, parsers, log changes; **iteration 3:** httpx timeout in `_streamable_http_factory`, `_classify_failure` MCPError/429 handling, backoff values, `FIRECRAWL_CONCURRENCY` sizing, queue-aware timeouts, new `batch_scrape` op + `BatchScrapeResult` + batch parser + batch tool constants; **iteration 4:** `ResolvedBatchTools` + `_resolve_firecrawl_batch_tools` + `_match_batch_tool` + batch candidate constants (replacing the fixed batch tool constants); `verify_capabilities` resolves+requires batch (M11); `_batch_identity` guard; `batch_scrape`/`_read_batch_job` call the resolved identity; `mcp.tools_listed` + batch diagnostics; **iteration 5:** rename `batch_scrape`→`scrape_pages` + `BatchScrapeResult`→`ScrapeResults` as a `scrape_page` fan-out (M13); add `_TokenBucket` + `FIRECRAWL_RATE_PER_MINUTE` acquired in `_single_call` on the Firecrawl path (A7); remove `_read_batch_job`/batch parsers/`BATCH_*` (R2), the resolver/`ResolvedBatchTools`/candidates/`_batch_identity`/`verify_capabilities` batch branch/batch logs (R3), and `_probe_firecrawl_shape` + its `open()` call (R4); keep `mcp.tools_listed`, `FIRECRAWL_PROBE_URL`, parsers | A1 to A3, M1, M2, R1, A4, M5 to M10, A5, M11, A6, M13, A7, R2, R3, R4 |
| 6 | `backend/src/services/deep_search/amenity_search.py` | No change | Injection and `aclose` are unaffected | |
| 7 | `test_place_discovery.py`, `test_accessibility_enrichment.py`, `test_result_attachment.py` | No change | Pass `tool_gateway=None` | |
| 8 | `feature_sample_runs/result_attachment_sample_run.py` | No change | Passes `tool_gateway=None` | |
| 9 | `backend/tests/services/deep_search/test_mcp_tool_gateway.py` | Modify | Fixture server serves map and scrape; capability, probe, map, scrape, concurrency cases; **iteration 3:** slow-stream-survives-timeout, MCPError->transport retry, 429-in-MCPError->rate_limited, longer backoff values, queue-aware timeout, batch-job fixtures; **iteration 4:** missing-batch-tool now fails at connect (M11); **iteration 5:** replace batch-job/missing-batch cases with `scrape_pages` fan-out + per-URL partial-failure + rate-pacing (≤10/min) cases; drop the probe cases (R4) | A1 to A3, M1 to M4, R1, A4, M5 to M10, M11, M13, A7, R2, R3, R4 |
| 10 | `feature_sample_runs/mcp_tool_gateway_sample_run.py` | Modify | Add map and scrape stages; crawl becomes opt-in; V2b on scrapes; **iteration 3:** a `batch_scrape` stage over mapped pages (the transport/call/header diagnostic tracers added this session already live here behind `--trace-calls`); **iteration 4:** `--batch-only` (probe + other stages skipped), `--trace-transport` (full relay), `--trace-calls` scoped to batch (M12); **iteration 5:** the batch stage calls `scrape_pages`→`ScrapeResults`; STAGE 1 drops the `mcp.probe_passed` print (R4); re-scope `--trace-calls` from `"batch"` to `firecrawl_scrape` | A1 to A3, M3, A4, M12, M13, A7, R4 |
| 11 | `feature_context/deep_search_context.md` | Modify | C3.1.1 section brought to the new spec | all |
| 12 | `feature_tests/test_c3_1_1_mcp_tool_gateway.py` (not in iteration-1 plan; in repo) | Modify | Same fixture and case changes as #9; **iteration 4:** missing-batch now fails at connect (M11); resolver unit tests `t62`-`t66` (canonical, renamed-via-substring, missing-start/status raise, missing send-arg raise, missing job-id arg → default + WARN); **iteration 5:** delete the resolver `t62`-`t66` and the connect-raise case (R3); replace batch-job cases with `scrape_pages` fan-out + partial-failure + rate-pacing; drop probe cases (R4); rename the fake's member/type | A1 to A3, M1 to M4, R1, A4, M5 to M10, A5, M11, M13, A7, R2, R3, R4 |
| 13 | `feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (not in iteration-1 plan; in repo) | Modify (docs) | Reword capability entries; add entries for the new cases; **iteration 3:** entries for M5-M10 and A4; **iteration 4:** entries for A5/M11 (batch resolution + connect-time requirement); **iteration 5:** replace the A4/A5/M11 entries with `scrape_pages` fan-out + A7 rate-pacing entries; drop probe entries | M1, R1, A1 to A3, A4, M5 to M10, A5, M11, M13, A7, R2, R3, R4 |

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
               ├─ Stage 3: probe Firecrawl output shape, one map and one scrape                  [A3 → REMOVED by R4]
               ├─ Stage 4: search_web, typed web_search on Parallel
               ├─ Stage 5: map_site, typed firecrawl_map on Firecrawl                            [A1]
               ├─ Stage 6: scrape_page, typed firecrawl_scrape on Firecrawl                      [A2]
               ├─ Stage 6b: scrape_pages, concurrent firecrawl_scrape fan-out over many URLs    [A4 → renamed by M13]
               ├─ Stage 7: crawl_site and status re-read, retained and unused by M3
               └─ Stage 8: aclose, close every session in its owner task
```

> **Iteration 5 annotation.** Stage 3 (the probe) is **removed** (R4): `open` now runs start-sessions → `verify_capabilities` only. Stage 6b `batch_scrape` is **renamed** to `scrape_pages` (M13) and is now a concurrent `scrape_page` fan-out, not a server-side batch job (the endpoint has no batch tool). A new shared-machinery gate, the per-minute Firecrawl token bucket [A7], sits beside `_firecrawl_sem` on the call path every Firecrawl stage uses — not a new stage.

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
| `ScrapeResults` **[A4 → renamed by M13]** (was `BatchScrapeResult`) | typed multi-page outcome of the fan-out | `pages: tuple[ScrapeResult, ...]` (one per URL, each keyed by its own `sourceURL`) · `total: int` · `completed: int` · `failed_urls: tuple[str, ...]` (per-URL misses) · `retrieved_at: str` | immutable | Stage 6b → C3.1.6 |
| `ToolFailure` | typed per-call failure, returned not raised | `tool` · `kind: tool_error \| timeout \| rate_limited \| transport \| unparseable` · `message` | immutable | Stages 4 to 7 → callers |
| `McpGatewayError` tree | gateway-level failure, raised | `McpConnectionError`, `McpToolUnavailableError`; `stage` is `open`, `verify_capabilities` or `verify_probe` **[A3]** | immutable | Stages 1 to 3 → run |

> Rules: an empty `links` list is a valid `MapResult`, and empty `text` with a `sourceURL` is a valid `ScrapeResult`; neither is a failure, so C3.1.4 can label them `empty`. A scrape body with no non-empty `sourceURL` is `ToolFailure(unparseable)`. `ScrapeResult.url` is `metadata.sourceURL` as reported; per Firecrawl's docs that is the URL that was requested (the post-redirect URL is the separate `metadata.url`, which is not carried), so callers key by it as a stable page key (not live-verified). `retrieved_at` is stamped when the operation starts, as in `search_web`. No new failure kind (`BatchScrapeResult` reuses `ScrapeResult` per page and `ToolFailure` for a whole-job failure). Keys appear only in `McpServerConfig.api_key`.
>
> **Iteration 3 [A4] rule:** `BatchScrapeResult` is a job wrapper, not a per-page type: each element of its `pages` is the existing `ScrapeResult`, keyed by the page's own `metadata.sourceURL` (not request order). A page that failed inside an otherwise-completed job is recorded in `failed_urls` (the batch's own error listing), not as a whole-job `ToolFailure`; an unreadable job envelope is `ToolFailure(unparseable)`.
>
> **Iteration 5 [M13] rule (supersedes the A4 rule above):** the type is renamed `ScrapeResults` and is the aggregate of a client-side fan-out, not a server job envelope. Its `pages` are the successful `ScrapeResult`s gathered from one `scrape_page` per URL; a URL whose scrape failed rides `failed_urls` (a signalled degrade), the rest complete. There is no job id, `next` cursor, or whole-job envelope to parse, so `_parse_batch_*` is gone (R2); only the field shape is carried over from `BatchScrapeResult`.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `ToolGateway` | Protocol | `open()` · `search_web(objective, search_queries)` · `map_site(url)` **[A1]** · `scrape_page(url)` **[A2]** · `scrape_pages(urls)` **[A4 → renamed by M13]** (was `batch_scrape`) · `crawl_site(url, limit, depth)` · `aclose()` | `McpToolGateway`, test fake | `AmenitySearch`; C3.1.3 to C3.1.7 later |
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
| `scrape_pages` **[A4 → renamed+rewritten by M13]** (was `batch_scrape`) | `(urls: Sequence[str], *, formats: Sequence[str] = ("markdown",)) -> ScrapeResults \| ToolFailure [raises: ValueError, McpConnectionError]` | fan out one `scrape_page` per URL concurrently; gather into `ScrapeResults` |
| `crawl_site` | `(url: str, limit: int, depth: int) -> CrawlResult \| ToolFailure [raises: ValueError, McpConnectionError]` | retained; start crawl, read the job by id |
| `aclose` | `() -> None` | idempotent; end every owner task |
| `_call_with_retry` **[A1, A2; +A7]** | `(semaphore, client, tool: str, arguments: dict, *, timeout: float, retry_kinds: set[str], target: str \| None = None, rate: _TokenBucket \| None = None) -> object \| ToolFailure` | one bounded call with transient retry; **[A7]** Firecrawl calls pass a token bucket, Parallel passes `None` |
| `_read_crawl_job` | `(client, job_id: str, url: str, retrieved_at: str) -> CrawlResult \| ToolFailure` | retained; poll or re-read the job by id |
| `_read_batch_job` **[A4 → REMOVED by R2]** | — | deleted; no job id to poll once `scrape_pages` fans out |

**`_ServerSession`** (private) is unchanged: `start`, `client`, `stop`; one owner task per server.

**Module-level pure functions** (no state, tested from fixtures):

| Function | Signature | Purpose (one line) |
| --- | --- | --- |
| `_parse_search_result`, `_parse_crawl_result`, `_parse_crawl_status`, `_decode_body` | unchanged | existing parsing and classification |
| `_classify_failure` **[M6, M7]** | `(error_or_result) -> ToolFailureKind` | map an exception or `is_error` result to a kind; now classifies `MCPError`(SSE-ended) as `transport` and a `429` embedded in an `MCPError` as `rate_limited` |
| `_streamable_http_factory` **[M5]** | `(config: McpServerConfig) -> AbstractAsyncContextManager[Client]` | default client factory; builds `httpx2.AsyncClient` with an explicit `timeout` matched to the call budget |
| `_parse_map_result` **[A1]** | `(result: CallToolResult, url: str, retrieved_at: str) -> MapResult [raises: _UnparseableResult]` | read `links` into typed candidates |
| `_parse_scrape_result` **[A2]** | `(result: CallToolResult, retrieved_at: str) -> ScrapeResult [raises: _UnparseableResult]` | read top-level `markdown` and `metadata.sourceURL` |
| `_parse_batch_scrape_result` **[A4 → REMOVED by R2]** | — | deleted with the job-envelope path; the fan-out reuses `_parse_scrape_result` per page |
| `_TokenBucket` **[A7]** (new, private) | `acquire() -> None` (async; `await`s until a token is free) · refills ~`FIRECRAWL_RATE_PER_MINUTE` tokens over a 60 s window | gateway-held per-minute throttle for the Firecrawl path; lock-guarded counter, monotonic refill |
| `_log_attempt` **[A1, A2]** | `(tool: str, attempt: int, failure: ToolFailure, target: str \| None = None) -> None` | record one failed attempt as WARN |
| `create_mcp_tool_gateway` **[A3]** | `(settings: Settings) -> McpToolGateway` | composition root; opens nothing; passes probe URL |

**Module constants** **[A1, A2, M1, M2, R1]**: add map and scrape tool names, their argument tuples, `MAP_TIMEOUT_SECONDS`, `SCRAPE_TIMEOUT_SECONDS`, `FIRECRAWL_PROBE_URL_DEFAULT`; rename `CRAWL_CONCURRENCY` to `FIRECRAWL_CONCURRENCY`; remove `FIRECRAWL_CRAWL_ARGS` (no reader once the check drops crawl). Keep `FIRECRAWL_CRAWL_TOOL`, `FIRECRAWL_STATUS_TOOL`, `FIRECRAWL_STATUS_JOB_ARG` for the retained crawl path.

**Module constants (iteration 3)** **[A4, M8, M9, M10]**, with the agreed starting values:
- `BATCH_MAX_CONCURRENCY = 2` [A4, M9]; `BATCH_DEADLINE_SECONDS = 300.0`, `BATCH_POLL_INTERVAL_SECONDS = 5.0` [A4, M10]; batch-scrape / batch-status / batch-errors tool names and their job-id argument (names read from the authenticated `tools/list` at build time, OV-11).
- Retry backoff split by kind [M8]: keep `RETRY_BACKOFFS_SECONDS = (2.0, 3.0)` for `timeout`/`transport`; add `RATE_LIMIT_BACKOFFS_SECONDS = (30.0, 60.0)` used for `rate_limited`, overridden by a response `Retry-After` when present; 2 retries / 3 attempts retained.
- `FIRECRAWL_CONCURRENCY = 2` (plan browser limit) [M9]; `SEARCH_CONCURRENCY = 4` unchanged.
- `MAP_TIMEOUT_SECONDS = 60.0`, `SCRAPE_TIMEOUT_SECONDS = 60.0` (raised from 45/30), queue-inclusive [M10]; `SEARCH_TIMEOUT_SECONDS = 30.0`, `CRAWL_CALL_TIMEOUT_SECONDS = 60.0`, `CRAWL_DEADLINE_SECONDS = 180.0`, `CRAWL_POLL_INTERVAL_SECONDS = 3.0` kept.

These remain unmeasured starting values; the rate-window figure (OV-8) and the queue-inclusive budgets (OV-10) are confirmed on the runner, and the batch tool names at build time (OV-11).

**Iteration 5 blueprint deltas (M13, A7, R2, R3, R4).**
- **`open` [A3 → R4]:** drops the `_probe_firecrawl_shape` step; the body becomes start-sessions → `verify_capabilities`.
- **`verify_capabilities` [M11 → R3]:** drops the batch resolve+require branch and `self._batch_tools`; requires only `web_search` / `firecrawl_map` / `firecrawl_scrape` again.
- **`_single_call` [A7]:** on the Firecrawl path, `await`s a `_TokenBucket` token in addition to the `_firecrawl_sem` slot (both held only across the live call); the Parallel path takes no token.
- **`scrape_pages` [M13]:** fan-out body — `gather` one `scrape_page(u)` per URL with `return_exceptions=True`; successes → `ScrapeResults.pages`, per-URL failures → `failed_urls`.
- **Removed [R2/R3/R4]:** `_read_batch_job`, `_parse_batch_start`/`_parse_batch_status`, `_resolve_firecrawl_batch_tools`, `_match_batch_tool`, `ResolvedBatchTools`, `_batch_identity`, `_probe_firecrawl_shape`.
- **Constants:** add `FIRECRAWL_RATE_PER_MINUTE = 10` (+ 60 s window) [A7]; remove `BATCH_MAX_CONCURRENCY`/`BATCH_DEADLINE_SECONDS`/`BATCH_POLL_INTERVAL_SECONDS` [R2] and `FIRECRAWL_BATCH_*_CANDIDATES`/`FIRECRAWL_BATCH_START_ARGS` [R3]. Keep `FIRECRAWL_PROBE_URL_DEFAULT` (the probe method is gone, the setting stays [R4]).

## E. Runtime Flow: Data Object Journey

Request path (runner and fixtures excluded). Unchanged stages are listed so the order is readable.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `open` → `_ServerSession.start` x2 | two `McpServerConfig` | one owner task and one `Client` per server | both sessions ready |
| 2 | `verify_capabilities` **[M1, R1]** | `tools/list` from each server | pass or `McpToolUnavailableError` | catalogs checked |
| 3 | `_probe_firecrawl_shape` **[A3 → REMOVED by R4]** | — | step deleted; `open` goes straight from `verify_capabilities` to serving calls | (no probe) |
| 4 | `search_web` | objective, queries | `WebSearchResult` or `ToolFailure` | typed excerpts |
| 5 | `map_site` **[A1]** | homepage url | `MapResult` or `ToolFailure` | typed candidate links |
| 6 | `scrape_page` **[A2]** | page url | `ScrapeResult` or `ToolFailure` | typed page keyed by source URL |
| 6b | `scrape_pages` **[A4 → M13]** (was `batch_scrape` + `_read_batch_job`) | list of page urls | `ScrapeResults` or `ToolFailure` | typed pages keyed by source URL, counts, failed urls |
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

**Iteration 5 trace deltas (M13, A7, R2, R4):**
```
(urls)                                                          # scrape_pages  [M13]
 → gather( scrape_page(u) for u in urls ), return_exceptions=True
 → successes → ScrapeResults.pages (each ScrapeResult keyed by sourceURL)
 | per-URL failure → failed_urls (signalled degrade, WARN) ; the rest complete
   (no start envelope, no job id, no `next` cursor — the A4 batch path is gone [R2])

(any Firecrawl call: map / scrape / crawl)                      # rate pacing  [A7]
 → _single_call acquires _firecrawl_sem (≤ 2)  AND  a token from _TokenBucket (≤ 10/min)
 → no token → await until the 60 s window refills, then proceed   # queue-and-pace, never dropped
   (Parallel web_search takes no token)

(open)                                                          # probe removed [R4]
 → start sessions → verify_capabilities → serve calls            # no map/scrape at connect
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

**Iteration 5 method detail (supersedes the `batch_scrape`/`_read_batch_job` [A4] and `_probe_firecrawl_shape` [A3] detail above).**

**`scrape_pages` [M13]** (was `batch_scrape`)
- **Purpose:** fetch the app-shortlisted URLs by running one single-page scrape per URL concurrently, since the endpoint exposes no batch tool.
- **What it does:** validate the list (non-empty; each a non-empty `http(s)` URL, same rule as `scrape_page`); `gather` one `scrape_page(u)` per URL with `return_exceptions=True`; collect successes into `ScrapeResults.pages` (each keyed by its own `sourceURL`), and the URLs whose scrape returned a `ToolFailure` (or raised) into `failed_urls`. Concurrency is bounded automatically because each `scrape_page` takes a slot from `_firecrawl_sem` and a token from the A7 bucket; no separate batch concurrency arg.
- **Failure:** bad input → `ValueError`; session-not-open propagates `McpConnectionError`; otherwise never a whole-call failure — a per-URL miss rides `failed_urls` (signalled degrade). An all-failed list still returns `ScrapeResults` with empty `pages` and a full `failed_urls`.

**`_TokenBucket` and `_single_call` rate gating [A7]**
- **Purpose:** keep the gateway inside Firecrawl's per-minute limit (10/min on `/scrape`, per key, team-shared) proactively, instead of firing over the limit and retrying `429`s.
- **What it does:** `_TokenBucket` holds up to `FIRECRAWL_RATE_PER_MINUTE` tokens, refilling across a 60 s window (monotonic clock), its counter guarded for the concurrent `gather`. In `_single_call`, a **Firecrawl** call `await`s one token after taking the `_firecrawl_sem` slot (both released at the call's end); if no token is free it sleeps until the window refills. It is one shared bucket for **all** Firecrawl calls (map/scrape/crawl), passed in like the semaphore; the **Parallel** path passes `None` and takes no token.
- **Placement vs the call timeout:** the token wait is **outside** the per-call `asyncio.timeout` (waiting for the window is not the call being slow), so a paced call is not falsely timed out; the live call stays bounded by its own budget once it starts.
- **Scope:** the bucket is gateway-**instance** state, so one shared gateway paces all concurrent amenities (the "one gateway per run" invariant is a C3.1.7 handoff). Cross-process/team-wide pacing is out of scope; the reactive `429` backoff (M7/M8) stays as that backstop.

**`verify_capabilities` [R3 delta]:** drops the batch resolve+require branch (`_resolve_firecrawl_batch_tools` / `self._batch_tools`); it again matches only `web_search`, `firecrawl_map`, `firecrawl_scrape` and leaves crawl/status/batch unchecked.

**`open` [R4 delta]:** drops `_probe_firecrawl_shape`; the body is start-sessions → `verify_capabilities`. The teardown guard is unchanged. A wrong Firecrawl output shape (if it ever recurs) surfaces per-call as `ToolFailure(unparseable)` from `_parse_scrape_result`/`_parse_map_result`, not at connect.

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

### Iteration 5 drift entries (supersede the `batch_scrape` and `_probe_firecrawl_shape` entries above)

The `batch_scrape`/`_read_batch_job` [A4] and `_probe_firecrawl_shape` [A3] drift entries no longer apply (R2/R4 delete those methods). New/changed entries:

#### `scrape_pages` [M13]
**Core behavior:** fan out one `scrape_page` per URL, gather into `ScrapeResults`.
**Drifts handled:**
- **Bad input.** Empty list, or a non-`http(s)`/empty URL in it. Caught at the method **edge**. **Rejected** with `ValueError`, matching `scrape_page`.
- **Session not open.** Caught in the core via `client()` (through each `scrape_page`). **Propagated** as `McpConnectionError`.
- **A single URL's scrape fails/times out.** Each `scrape_page` already recovers via retry then returns a `ToolFailure`. Caught in the core by `gather(..., return_exceptions=True)`. **Recovered (degrade, signalled):** the URL rides `failed_urls`, the rest complete; one WARN `mcp.scrape_pages_partial` records the count. Never a whole-call failure.
- **`gather` default fail-fast.** `gather` without `return_exceptions` propagates the first failure and orphans the siblings. Technical-choice drift. Caught in the core. **Recovered** by `return_exceptions=True` so each URL is judged on its own.
- **A slow URL.** Bounded by each `scrape_page`'s `SCRAPE_TIMEOUT_SECONDS`; the call ends when the slowest gathered scrape settles. **Recovered** (per-call timeout).
**Left out (why):**
- Splitting a large URL list, per-URL retry beyond the gateway, host-filter/dedup: C3.1.6 owns fan-out shaping and the call cap. *Wrong boundary.*
- Capping list length here: C3.1.6 applies the 50-candidate cap upstream. *Wrong boundary.*

#### `_TokenBucket` / `_single_call` rate gating [A7]
**Core behavior:** admit ≤`FIRECRAWL_RATE_PER_MINUTE` Firecrawl calls per 60 s window, waiting when the budget is spent.
**Drifts handled:**
- **Concurrent counter mutation.** The fan-out `gather`s many coroutines that all take tokens at once. Shared-mutable-state drift. Caught in the **core** bucket. **Guarded** by a lock (or atomic compare) and a monotonic refill clock, so no two coroutines double-spend a token.
- **Over-budget burst.** A fan-out (or several concurrent amenities) wants more than 10 starts/min. Technical-choice drift of the limiter. Caught in `_single_call`. **Recovered** by `await`ing until the window refills (queue-and-pace), never dropping a call.
- **Token wait vs per-call timeout.** If the bucket wait sat inside the call's `asyncio.timeout`, a paced call would be falsely timed out. Caught by placement. **Rejected** by keeping the token wait outside the per-call timeout.
- **Wrong server throttled.** Applying the Firecrawl bucket to a Parallel `web_search` call would wrongly throttle it to 10/min. Caught at the call site. **Rejected** by passing the bucket only on the Firecrawl path (Parallel passes `None`).
**Left out (why):**
- Cross-process / team-wide pacing: a token bucket in our process cannot see a teammate's process on the same key. *Wrong boundary* (the reactive `429` backoff is the backstop).
- Per-endpoint buckets (separate for map vs scrape): the 10/min is per key, not per endpoint; one shared bucket is correct. *Imaginary (not the real limit shape).*
- Logging the token wait: a wait is normal pacing, not a drift. *Not a node* (cost check, see H).

#### `verify_capabilities` [R3 delta] / `open` [R4 delta]
- `verify_capabilities` loses the batch resolve+require drift (no batch tool resolved/required anymore); its remaining drifts (renamed/removed required tool → reject; listing unreachable → propagate) are unchanged.
- `open` loses the probe drifts; its remaining drift (any failure/cancellation mid-open → close both sessions then propagate) is unchanged.

---

## H. Logging

Per the diagnostic-logger skill: one stream of structured lines, boundary crossings, silent drifts and state changes only; nothing narrates success. All lines use `DEEP_SEARCH_LOGGER_NAME` and are JSON, as the existing `mcp.*` events are.

| Event | Level | Node type | Fields | When |
| --- | --- | --- | --- | --- |
| `mcp.session_opened` | INFO | boundary | `server`, `authenticated` | per server at open (unchanged) |
| `mcp.probe_passed` **[A3 → REMOVED by R4]** | — | — | — | the probe is gone, so this line is removed |
| `mcp.call_attempt_failed` **[A1, A2]** | WARN (was INFO) | silent drift (recover) | `tool`, `attempt`, `kind`, `message`, `target` (map and scrape) | each failed attempt, retried or final (kept as the reactive-429 backstop) |
| `mcp.map_links_skipped` **[A1]** | WARN | silent drift (degrade) | `url`, `skipped`, `kept` | only when entries were skipped |
| `mcp.scrape_pages_partial` **[A4 → renamed by M13]** (was `mcp.batch_pages_failed`) | WARN | silent drift (degrade) | `total`, `completed`, `failed` | only when a `scrape_pages` fan-out has per-URL failures |
| `mcp.tools_listed` **[A6, kept]** | INFO | boundary | `server`, `tool_count`, `tools`, `args` | per server at `verify_capabilities` (the full catalog) |
| `mcp.probe_passed` scrape disconnect note **[M6]** | WARN | silent drift (recover) | `tool`, `attempt`, `kind="transport"` | each retried SSE-ended attempt, via the existing `mcp.call_attempt_failed` line (kind now `transport`, not `tool_error`) |

- **Rejects ride their exception.** Probe and capability failures are not logged again here; the exception message carries operation and kind, and the caller logs where it handles it.
- **Not logged:** every successful call, page text, link lists, anything derived from a key. The existing key-hygiene test keeps guarding keys and extends to the new tools.
- **Correlation.** Gateway lines carry `tool` and `target`. A per-amenity correlation id belongs to the pipeline that owns the amenity (C3.1.6/C3.1.7); the gateway has no amenity context. Handoff, not built here.
- **Level change.** A failed attempt that is retried is a handled drift, hence WARN. No test asserts the old INFO level.
- **Iteration 5 logging [M13, A7, R3, R4].** Removed with their code: `mcp.probe_passed` (R4) and the batch-resolution logs `mcp.batch_tools_resolved` / `mcp.batch_arg_unresolved` / `mcp.batch_resolution_failed` / `mcp.batch_pages_truncated` (R3). Kept: `mcp.tools_listed` (A6, a general capability-boundary log, not batch-specific). The A7 token wait is **not** logged — a paced wait is normal throughput shaping, not a drift or a boundary (cost check); the reactive `mcp.call_attempt_failed` on an actual `429` remains the only rate-related line.

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

**Iteration 5 sample-runner & fixture deltas (M13, A7, R2, R3, R4).**
- **Runner (#10):** STAGE 4b calls `gateway.scrape_pages(urls)` and prints `ScrapeResults` (per-page `url`/length, `total`/`completed`, `failed_urls`); STAGE 1 drops the `mcp.probe_passed` print (R4); `--trace-calls` scoping moves from the `"batch"` substring to `firecrawl_scrape` (there are no batch-named calls now).
- **Fixtures (#9, #12):** drop the probe-pass / probe-shape-fail / probe-call-fail cases (R4) and the batch-job / resolver `t62`–`t66` / connect-raise cases (R2, R3). Add: a `scrape_pages` fan-out over several fixture URLs returns a `ScrapeResults` keyed by `sourceURL`; one URL's scrape failing rides `failed_urls` (+ `mcp.scrape_pages_partial`) while the rest complete; in-flight Firecrawl calls never exceed `FIRECRAWL_CONCURRENCY`; and an **A7 pacing** case — a fan-out wider than `FIRECRAWL_RATE_PER_MINUTE` is admitted ≤10 per window (assert start timestamps/spacing with a controllable clock), and the Parallel `web_search` path takes no token. The key-hygiene case runs a map, a scrape and a `scrape_pages`.

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

### Architecture & Modularity Decisions — Iteration 5 (M13, A7, R2, R3, R4)

**C. Decisions & Justifications (added this iteration)**

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| `scrape_pages` as a concurrent `scrape_page` fan-out (M13), replacing the batch job | the hosted `/v2` endpoint exposes no batch tool; M3 must still fetch a shortlist of URLs | `batch_scrape` fails on every run (`-32601 Unknown tool`) |
| Rename `batch_scrape`→`scrape_pages`, `BatchScrapeResult`→`ScrapeResults` (M13) | the name must state the mechanism (N single scrapes), not imply a server job | callers carry a name that misleads about transport |
| `_TokenBucket` per-minute limiter in `_single_call`, Firecrawl path (A7) | Firecrawl Free = 10 `/scrape` per minute per key (team-shared); the fan-out routinely exceeds it | the gateway bursts past 10/min, trips `429`s, churns on reactive backoff |
| Both gates (sem + bucket) as gateway-**instance** state | the per-key limit is global; all concurrent amenities must share one budget | per-amenity limiters would allow 2×N in-flight and 10×N/min |

**D. Kept Concrete / Rejected (added this iteration)**

| Considered | Decision | Reason |
| --- | --- | --- |
| A `RateLimiter` interface for the limiter | rejected | one concrete token bucket, one consumer (`_single_call`); an interface with one implementer is over-engineering |
| Separate per-endpoint buckets (map vs scrape) | rejected | the 10/min is per key, not per endpoint; one shared bucket is the real shape |
| Distributed / cross-process limiter (shared store) | not added | out of scope; the reactive `429` backoff covers the cross-process slice |
| Keep the A4 batch machinery / A5 resolver "for a future self-hosted batch server" | rejected | speculative; no current requirement — removed (R2/R3), reintroduce if that server is adopted |
| Keep the connect-time probe "in case the shape regresses" | rejected | a live run confirmed the 3.x shape; a regression surfaces per-call as `unparseable`; the probe only cost two billed calls per `open` (R4) |

**Over-engineering guard — elements added this iteration**

| Element | One-line justification |
| --- | --- |
| `scrape_pages` fan-out (no new abstraction) | reuses `scrape_page` + `asyncio.gather`; only new surface is the renamed `ScrapeResults` (same fields as `BatchScrapeResult`) |
| `_TokenBucket` (concrete, private) | the per-key 10/min must be enforced at the shared chokepoint; a plain counter+monotonic clock, no library, no interface |
| `FIRECRAWL_RATE_PER_MINUTE = 10` | the limit must change without a code edit; one constant at the composition root |

**G. Async map — replaces the "Batch scrape call path [A4]" row**

| Operation group | Operations and I/O | Data dependency | Placement | Ordering | Shared-state handling | Blocking / worker |
| --- | --- | --- | --- | --- | --- | --- |
| `scrape_pages` fan-out **[M13, A7]** | one `scrape_page` per URL; each: `_firecrawl_sem` wait, `_TokenBucket` token wait, `call_tool`, backoff | URLs independent; retry within one scrape depends on its prior attempt | event loop | **concurrent** (`gather`, `return_exceptions=True`); throttled to ≤2 in-flight (sem) and ≤10/min (bucket) | shared Firecrawl pool + shared token bucket (lock-guarded counter) bound all in-flight Firecrawl work; results returned per URL | none; async-native `httpx2`, no worker. The token wait is an on-loop `await` (sleep until refill), outside the per-call timeout |

**F. Composition root — Selects (iteration 5 delta):** add `FIRECRAWL_RATE_PER_MINUTE = 10` (60 s window); remove `BATCH_DEADLINE_SECONDS`/`BATCH_POLL_INTERVAL_SECONDS`/`BATCH_MAX_CONCURRENCY` and the batch tool-name candidates; `open` no longer runs the probe.

**Layer 4 backing (iteration 5):**
- **Fan-out over a batch job:** the endpoint has no batch tool, and the shortlist is specific, often cross-domain URLs — only per-URL scraping fetches exactly those; `firecrawl_crawl` (one-domain discovery) is the wrong shape. At the 2-browser limit the throughput matches a batch's `maxConcurrency=2`.
- **Limiter at the shared chokepoint [A7]:** the 10/min is a property of the key, so it is enforced where every Firecrawl call funnels (`_single_call`), as instance state a single shared gateway owns. "One gateway per run" is a C3.1.7 handoff; a distributed limiter is deferred.

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
| OV-8 | Confirm the rate-limit backoff window [M8] | **Closed.** Firecrawl Free = **10 requests/minute on `/scrape`, shared across the team's keys**. Decision: add a **proactive per-minute token bucket** (`FIRECRAWL_RATE_PER_MINUTE = 10`) on the Firecrawl path in `_single_call`, beside `_firecrawl_sem`, as shared gateway-instance state — so a call waits for the window instead of firing and taking a `429` (A7, pending fix; see the Iteration 4 report). Keep the reactive `Retry-After`/`(30,60)` backoff as the cross-process backstop. Parallel `web_search` is unaffected (separate server/key). |
| OV-9 | `FIRECRAWL_CONCURRENCY` vs batch `maxConcurrency` [M9, A4] | **Retired by iteration 5 (R2).** `BATCH_MAX_CONCURRENCY` is removed with the batch job; `scrape_pages` is bounded only by `FIRECRAWL_CONCURRENCY = 2` (and the A7 ≤10/min bucket). Residual: confirm Free = 2 browsers still holds on the account's plan. |
| OV-10 | Confirm the queue-inclusive timeout values [M10] | **Starting values set:** map 60 s, scrape 60 s; **the batch deadline/poll are removed (R2)** — each fanned-out scrape uses the 60 s scrape budget. Residual: measure start-to-complete time (including queue wait) on the runner under the 2-browser limit and tighten. |
| OV-11 | Exact batch-scrape MCP tool names and arguments [A4] | **Retired by iteration 5 (R2/R3).** The authenticated `/v2` session has **no batch tool** (28 tools, none `batch`), so there is nothing to resolve; `scrape_pages` fans out `firecrawl_scrape` and the A5 resolver is removed. |
| OV-13 | Confirm the 10/min window shape for the A7 bucket [A7] | **Figure set:** `FIRECRAWL_RATE_PER_MINUTE = 10` on `/scrape`, team-shared. Residual: confirm on the runner whether the window is a fixed 60 s bucket or a sliding/rolling minute, and whether `firecrawl_map` draws from the same per-key budget; tune the bucket if the live `429` pattern differs. |
| OV-12 | Vendor: does the MCP endpoint support GET-based SSE resume (it answered `405`)? [M6] | confirm with Firecrawl; M5/M6 make the gateway resilient regardless |

## Handoffs to later sub-components

| To | What the gateway guarantees or leaves to it |
| --- | --- |
| C3.1.3 | passes app-injected homepage URL to `map_site` and the id-resolved URL to `scrape_page`; the gateway does no host check |
| C3.1.4 | empty `links` and empty `text` arrive as valid results, never failures; timeouts and parse misses arrive as `ToolFailure` |
| C3.1.6 | applies the 50-candidate cap, URL dedup and fan-out; keys evidence by the returned `ScrapeResult.url` (per Firecrawl's docs the requested URL; not live-verified); calls `scrape_pages(urls)` (concurrent `scrape_page` fan-out) for Phase-2 multi-page scraping [M13], and keeps the URL list within the plan limit alongside the gateway's own caps [M9, A7] |
| C3.1.6/C3.1.7 | owns the per-amenity correlation id for log lines; counts gateway-internal retries when it reasons about call caps |
| C3.1.7 | **shares one `McpToolGateway` per run across all concurrent amenities** so the Firecrawl concurrency semaphore (≤2) and the A7 per-minute bucket (≤10/min) bound the account globally; constructing a gateway per amenity would multiply both caps by the amenity count [A7, F26] |

---

# Appendix: C3.1.1 Iteration Report (the iteration-5 change spec)

> Replaces the earlier iteration-3 report. This is the stage-one report (per `skills/iteration_report.md`) that Iteration 5 implements. Report-local IDs map to this plan's ID space: **report A7 → plan A7**, **M1 → M13**, **R1 → R2**, **R2 → R3**, **R3 → R4**. The "Iteration 4 (as built)" appendix that follows is kept as the baseline this report reverts.

# C3.1.1 Spec Iteration Report — `batch_scrape` → `scrape_pages`: MCP batch job replaced by a concurrent `scrape_page` fan-out

> **Naming decision (user).** The public op and its contract are **renamed** to match the mechanism, not just rewritten under the hood: `batch_scrape` → **`scrape_pages`**, `BatchScrapeResult` → **`ScrapeResults`**. Plural forms are used deliberately because the singular `scrape_page(url)` / `ScrapeResult` already exist as the single-page operation this fan-out calls; `scrape_pages` / `ScrapeResults` are new, distinct names that cannot collide with them.

## 1. Confirmation

Inputs read (finalized pass — the plan is now updated through iteration 4):
- **Old spec** — the C3.1.1 block in `feature_context/deep_search_context.md`, excluding the "Fixes needs to be incorporated in iteration" section. (Its body is now written as iteration-4-as-built: batch required + resolved at connect.)
- **Implementation plan** — `r2_mechanism_3_c3_1_1_implementation_plan.md`, **now carrying the Iteration 4 appendix** (A5, M11, A6, M12) plus the iteration-3 body (A4, M5–M10). Artifact numbers `#1…#13`.
- **New spec** — the old spec **plus** the "Fixes needs to be incorporated in iteration" section at the end of the C3.1.1 block.

**"Implemented" = old spec + plan through iteration 4.** The baseline therefore already includes, as plan-documented and in-code artifacts (not interim):
- **A4** — `batch_scrape` as an MCP batch job (start → `_read_batch_job` poll → `BatchScrapeResult`).
- **A5** — batch tool names + job-id/cursor args resolved from the live `tools/list` (`ResolvedBatchTools`, `_resolve_firecrawl_batch_tools`, `_match_batch_tool`, `FIRECRAWL_BATCH_*_CANDIDATES`), replacing the fixed batch constants.
- **M11** — `verify_capabilities` resolves **and requires** the batch tools at connect; unresolvable → `McpToolUnavailableError`.
- **A6** — connect/resolution diagnostics (`mcp.tools_listed`, `mcp.batch_tools_resolved`, `mcp.batch_arg_unresolved`, `mcp.batch_resolution_failed`, `mcp.batch_pages_truncated`).
- **A3** — the connect-time `_probe_firecrawl_shape`.

The repo **was** available; artifact names come from the plan (`#n` / A-M IDs). Symbols not named in the plan are marked `(illustrative)`.

**What changed from the earlier draft of this report.** The earlier draft was written against the *pre-iteration-4* plan, so it treated A5/M11 as "interim work this session, not in the plan" and framed their removal as `(inferred)`. The plan now documents A5/M11/A6 as built, so this pass reclassifies them as first-class baseline artifacts whose removal is explicit (R2), and corrects the current-flow (§2) to show batch **is** resolved+required at connect in the as-built state.

**Counts:** 1 ADD · 1 MODIFY (code) + 2 MODIFY (tests/docs) · 3 REMOVE · 0 DECISION-GATED · 7 Flags.

---

## 2. Current traceflow, change locations

```
caller ──► McpToolGateway.open()                                   mcp_tools.py (#5)
│
├─ _start_sessions
├─ verify_capabilities                                             (#5)
│    ├─ require web_search / firecrawl_map / firecrawl_scrape
│    ├─ _resolve_firecrawl_batch_tools(catalog)  [A5]                           ◄── R2
│    │    └─ unresolvable ──► McpToolUnavailableError  [M11]                    ◄── R2
│    └─ mcp.tools_listed / batch_tools_resolved / batch_resolution_failed [A6]  ◄── R2
├─ _probe_firecrawl_shape ──► map_site + scrape_page  [A3]                      ◄── R3
│
caller ──► McpToolGateway.batch_scrape(urls)                       (#5) [A4]   ◄── M1
├─ call self._batch_tools.start_tool (resolved name)  [A5]                     ◄── R2
├─ _parse_batch_start ──► BatchScrapeResult | job_id                           ◄── R1
└─ _read_batch_job(job_id)                                                     ◄── R1
     ├─ poll self._batch_tools.status_tool by id + cursor arg                  ◄── R1
     ├─ _parse_batch_status ──► pages | still running | unparseable            ◄── R1
     ├─ follow next cursor                                                     ◄── R1
     └─ ──► BatchScrapeResult(pages keyed by sourceURL, failed_urls)
```

| ID | Class | Summary |
|----|-------|---------|
| A7 | ADD | proactive Firecrawl rate limiter: ≤2 in-flight (existing sem) **+** ≤10/min token bucket, Firecrawl-path only |
| M1 | MODIFY | rename `batch_scrape`→`scrape_pages`, `BatchScrapeResult`→`ScrapeResults`; body → concurrent `scrape_page` fan-out |
| R1 | REMOVE | batch job-envelope poll machinery [A4] (`_read_batch_job`, batch parsers, deadline/poll constants) |
| R2 | REMOVE | batch tool resolution + connect requirement [A5, M11, A6 batch logs]: `ResolvedBatchTools`, `_resolve_firecrawl_batch_tools`, candidates, `_batch_identity`, the `verify_capabilities` batch branch |
| R3 | REMOVE | connect-time Firecrawl shape probe [A3] (`_probe_firecrawl_shape`) |
| M2 | MODIFY | batch test cases (#9, #12): job-poll/cursor/resolver(`t62`–`t66`)/connect-raise → fan-out + partial-failure |
| M3 | MODIFY | docs: context (#11) capability + batch bullets; test plan (#13) A4/A5/M11 entries |

---

## 3. ADD points

### A7: proactive Firecrawl rate limiter (≤2 in-flight + ≤10 calls/minute), Firecrawl-path only

The fan-out (M1) makes it routine to exceed Firecrawl's **10 requests/minute** (Free plan, documented for `/scrape`, shared across the team's keys). Today only the **concurrency** cap exists (`_firecrawl_sem = 2`); there is no *throughput* cap, so a fan-out fires faster than 10/min, trips `429`s, and leans on the reactive 30/60 s backoff. A7 adds a **proactive per-minute token bucket** beside the existing semaphore so Firecrawl starts are paced, not retried-after-failure.

**Decision: both gates apply to ALL Firecrawl calls (`map_site` + `scrape_page`, and the retained `crawl_site`) — not scrape-only.** The one token bucket is a single shared budget for the whole Firecrawl path, so a `map_site` and a `scrape_pages` burst contend for the same 10/min (intended — the account limit is per key, not per endpoint). Parallel `web_search` is on a different server/key and is excluded.

Scope kept to C3.1.1 (the gateway owns "talk to Firecrawl safely"); the orchestration invariant and cross-process enforcement are **not** built here (see F2-handoff and F7).

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · Firecrawl token-bucket limiter (illustrative: `self._firecrawl_rate`), `FIRECRAWL_RATE_PER_MINUTE = 10` constant | add: gateway-**instance** state (like `_firecrawl_sem`), so one shared gateway paces all concurrent amenities together. ~10 tokens refilling over a 60 s window. |
| `mcp_tools.py` (#5) · `_single_call` | modify: on the **Firecrawl path** (every Firecrawl tool call — `firecrawl_map`, `firecrawl_scrape`, `firecrawl_crawl`), take a rate token in addition to the semaphore slot; if none is available, `await` until the window refills, then call. Passed as an argument like the semaphore, so the Parallel/`web_search` path takes no token. |
| `mcp_tools.py` (#5) · reactive 429 handling (M7/M8) | check only: kept as the cross-process backstop — a teammate's process on the same key can still push the shared total over 10/min, which our bucket cannot see. |
| tests (#9, #12) | add: a fan-out larger than the per-minute budget is **paced** (starts ≤10/min) rather than 429'd; `web_search` is unaffected by the Firecrawl bucket. |
| docs (#11, #13) | modify: record the proactive limiter and the 10/min figure (closes OV-8). |

BEFORE (iteration-4 as built — concurrency cap only, reactive rate handling)
```
_single_call (any Firecrawl call: map / scrape / crawl)
└─ acquire _firecrawl_sem (≤ 2)
     └─ call_tool (firecrawl_map | firecrawl_scrape | …)
          └─ > 10/min ──► 429 ──► classify rate_limited ──► backoff 30/60 s ──► retry
```

AFTER
```
_single_call (any Firecrawl call: map / scrape / crawl)
├─ acquire _firecrawl_sem (≤ 2)              (concurrency gate, existing)
└─ take a rate token (≤ 10 / min, shared across ALL Firecrawl calls)   ◄── NEW
     ├─ no token ──► await until window refills, then proceed          ◄── NEW
     └─ call_tool (firecrawl_map | firecrawl_scrape | …)
          └─ 429 (cross-process only) ──► reactive backoff kept  (backstop)
_single_call (Parallel web_search call)
└─ acquire _search_sem (≤ 4) only — no rate token                (unchanged)
```

Behaviour change: every Firecrawl call (map, scrape, crawl) is proactively paced to ≤10/min total and ≤2 concurrent; an over-budget call waits (never dropped, rarely 429'd). `web_search` keeps its own `_search_sem(4)` and is untouched by the Firecrawl bucket.

---

## 4. MODIFY points

### M1: rename `batch_scrape` → `scrape_pages`, `BatchScrapeResult` → `ScrapeResults`; body becomes a concurrent `scrape_page` fan-out

The op is renamed to state the mechanism (N concurrent single-page scrapes), not a server-side batch job. Because the name/contract change, the Protocol member, the C3.1.6 caller, and the test fake change with it.

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `McpToolGateway.batch_scrape` → `scrape_pages(urls, *, formats)` [A4] | rename + rewrite: new name; body `gather`s one `scrape_page(url)` per URL, each acquiring the existing `_firecrawl_sem`, with `return_exceptions=True`; a failed URL rides `failed_urls`, the rest complete. Needed because the hosted `/v2` server offers no batch tool. |
| `mcp_tools.py` (#5) · `BatchScrapeResult` → `ScrapeResults` [A4] | rename: the multi-page contract keeps its fields (`pages: tuple[ScrapeResult, …]`, `total`, `completed`, `failed_urls`, `retrieved_at`); only the type name changes. Distinct from the singular `ScrapeResult` it wraps. |
| `mcp_tools.py` (#5) · `ToolGateway.scrape_pages` Protocol member [A4] | rename: the Protocol member and its return type are renamed so the fake and callers see `scrape_pages(...) -> ScrapeResults`. |
| `amenity_search.py` / C3.1.6 caller (#6) · `batch_scrape` call site | rename: the Phase-2 fan-out caller calls `scrape_pages`; it already keys evidence by `ScrapeResult.url`, so only the method/type names change, not the handoff shape. |
| test fake `ToolGateway` (#9, #12) | rename: the fake's `batch_scrape` → `scrape_pages` returning `ScrapeResults`. |

BEFORE
```
McpToolGateway.batch_scrape(urls)
├─ validate urls
├─ call Firecrawl batch-scrape tool (one job)
├─ _parse_batch_start ──► BatchScrapeResult (inline) | job_id
└─ _read_batch_job(job_id)              ──► BatchScrapeResult(pages, failed_urls)
```

AFTER
```
McpToolGateway.scrape_pages(urls)                            ◄── RENAMED
├─ validate urls
├─ gather scrape_page(url) for each url                      ◄── NEW
│    ├─ each acquires _firecrawl_sem (2-browser cap)         ◄── NEW
│    └─ return_exceptions=True                               ◄── NEW
├─ failed url ──► failed_urls (degrade, logged)              ◄── NEW
└─ ──► ScrapeResults(pages keyed by sourceURL, failed_urls)  ◄── RENAMED
```

Behaviour change: callers call `scrape_pages(urls)` and get a `ScrapeResults`; it makes no MCP batch call, running concurrent single-page scrapes bounded by the existing semaphore. The field shape of the result is unchanged, only the type name.

### M2: batch test cases (job/poll/cursor → fan-out + partial failure)

| Artifact | Change |
|---|---|
| `tests/services/deep_search/test_mcp_tool_gateway.py` (#9) · batch-job fixtures | modify: the cases that assert "polls a job to completion", "follows the `next` cursor", batch-status `unparseable`/`timeout` `ToolFailure`, and "missing batch tool …" are replaced by fan-out cases: N concurrent scrapes keyed by `sourceURL`, one scrape failing rides `failed_urls`, the rest complete. The job-envelope assertions no longer describe real behaviour. |
| `feature_tests/test_c3_1_1_mcp_tool_gateway.py` (#12) · same cases | modify: same replacement; the iteration-4 resolver unit tests `t62`–`t66` and the connect-time missing-batch test (plan #12, A5/M11) are removed with R2 (no batch tool to resolve/require). |
| `feature_sample_runs/mcp_tool_gateway_sample_run.py` (#10) · batch stage | rename: the stage calls `gateway.scrape_pages(urls)` and prints the same `ScrapeResults` fields; only the method/type names change, the stage logic is unchanged. |

BEFORE
```
test_mcp_tool_gateway.py
├─ batch polls a job to completion keyed by sourceURL
├─ batch follows the next cursor
├─ batch-status unparseable ──► ToolFailure
├─ batch-status timeout     ──► ToolFailure
└─ missing batch tool       ──► per-call ToolFailure
```

AFTER
```
test_mcp_tool_gateway.py
├─ fan-out scrapes N urls keyed by sourceURL   ◄── CHANGED
├─ one url fails ──► failed_urls, rest complete ◄── CHANGED
├─ concurrency bounded by _firecrawl_sem        ◄── CHANGED
├─ job-poll / cursor cases                       ◄── GONE
└─ batch-status unparseable/timeout cases        ◄── GONE
```

Behaviour change: tests prove per-URL concurrent scraping and partial-failure degrade instead of job polling.

### M3: docs — capability-check and batch bullets

| Artifact | Change |
|---|---|
| `feature_context/deep_search_context.md` (#11) · C3.1.1 "Capability check" bullet | modify: drop "and the batch-scrape tool" from the not-checked clause; `firecrawl_crawl` stays the only retained-but-unchecked Firecrawl tool. Batch is no longer an MCP tool, so there is no per-call batch-tool gap to describe. |
| `feature_context/deep_search_context.md` (#11) · C3.1.1 batch operation + "batch output shape" bullets | modify: rewrite to the fan-out (no job envelope, no cursor); see the updated spec in §10. |
| `feature_tests/C3_1_1_mcp_tool_gateway_test_plan.md` (#13) · A4 entries | modify: reword the A4 entries from batch-job/cursor cases to fan-out + partial-failure cases. |

BEFORE
```
C3.1.1 spec
├─ capability check: crawl AND batch tool retained, not checked
├─ batch_scrape: one Firecrawl batch job, poll by id
└─ batch output shape: job envelope {status,total,completed,next,data[]}
```

AFTER
```
C3.1.1 spec
├─ capability check: only crawl retained, not checked      ◄── CHANGED
├─ scrape_pages: concurrent scrape_page fan-out            ◄── CHANGED
└─ output shape: ScrapeResults = gathered pages + failed_urls ◄── CHANGED
```

Behaviour change: the spec documents a fan-out, and batch is dropped from the "retained-but-unchecked tool" list.

---

## 5. REMOVE points

### R1: batch job-envelope poll machinery

Code fate: **deleted**

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `_read_batch_job` [A4] | remove: no job id exists to poll once `scrape_pages` fans out scrapes. |
| `mcp_tools.py` (#5) · `_parse_batch_scrape_result` [A4] (code: `_parse_batch_start`, `_parse_batch_status` (illustrative)) | remove: nothing produces a batch job envelope to parse. |
| `mcp_tools.py` (#5) · `BATCH_DEADLINE_SECONDS`, `BATCH_POLL_INTERVAL_SECONDS`, `BATCH_MAX_CONCURRENCY` constants | remove: no job clock, no poll loop, no per-job concurrency arg; each scrape is bounded by `SCRAPE_TIMEOUT_SECONDS` and `_firecrawl_sem` instead. |

BEFORE
```
batch_scrape
└─ _read_batch_job(job_id)
     ├─ poll batch-status tool by id + cursor
     ├─ _parse_batch_status ──► pages | running | unparseable
     └─ follow next cursor ──► BatchScrapeResult
```

AFTER
```
scrape_pages
└─ job-envelope poll path removed   ◄── GONE
```

Behaviour change: there is no polling, deadline, or cursor paging; results are whatever the concurrent scrapes return.

### R2: batch tool resolution + connect-time requirement [reverts A5, M11, A6 batch logs]

Code fate: **deleted**

Reverts the plan's iteration-4 work: once `scrape_pages` fans out `firecrawl_scrape`, there is no batch tool name to resolve, require, or diagnose. OV-11 (the build-time name-reading that A5 implemented) retires with it.

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `_resolve_firecrawl_batch_tools`, `_match_batch_tool`, `ResolvedBatchTools` [A5] | remove: no batch tool name/args to resolve. |
| `mcp_tools.py` (#5) · `FIRECRAWL_BATCH_*_CANDIDATES`, `FIRECRAWL_BATCH_START_ARGS` [A5] | remove: candidate lists have no consumer. (The fixed `FIRECRAWL_BATCH_SCRAPE_TOOL`/`_STATUS_TOOL`/`_JOB_ARG`/`_CURSOR_ARG` were already dropped by A5, so nothing to remove there.) |
| `mcp_tools.py` (#5) · `verify_capabilities` batch branch, `self._batch_tools`, `_batch_identity` [M11] | remove: the connect-time resolve+require step and its guard go; `verify_capabilities` requires only `web_search`/`firecrawl_map`/`firecrawl_scrape` again. |
| `mcp_tools.py` (#5) · `mcp.batch_tools_resolved`, `mcp.batch_arg_unresolved`, `mcp.batch_resolution_failed`, `mcp.batch_pages_truncated` [A6] | remove: these log resolution and job-cursor degrades that no longer happen. `mcp.tools_listed` [A6] is **kept** — a general capability-boundary log, not batch-specific. |

BEFORE
```
verify_capabilities  [M11]
├─ require web_search / firecrawl_map / firecrawl_scrape
└─ _resolve_firecrawl_batch_tools(catalog)  [A5]
     ├─ match names (candidates → substring), resolve job-id/cursor args
     ├─ unresolvable ──► McpToolUnavailableError
     └─ ──► self._batch_tools  (+ A6 resolution logs)
batch_scrape / _read_batch_job
└─ call self._batch_tools.start_tool / .status_tool
```

AFTER
```
verify_capabilities
├─ require web_search / firecrawl_map / firecrawl_scrape
└─ batch resolution + requirement removed            ◄── GONE
scrape_pages
└─ no batch tool name used (fans out scrape_page)    ◄── GONE
```

Behaviour change: `verify_capabilities` no longer resolves or requires a batch tool, and a server with no batch tool (the live case) no longer fails at connect; `scrape_pages` carries no batch tool name.

### R3: connect-time Firecrawl shape probe

Code fate: **deleted**

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `_probe_firecrawl_shape` [A3] | remove: delete the method and its call in `open()`. A live run confirmed the hosted `/v2` server returns the 3.x JSON shape we parse, so the two billed probe calls (one `map_site` + one `scrape_page`) per `open()` re-confirm something already verified. |
| `mcp_tools.py` (#5) · `open()` sequence [A3] | modify: `open()` becomes start-sessions → `verify_capabilities`, with no probe step after the capability check. |
| `tests/services/deep_search/test_mcp_tool_gateway.py` (#9), `feature_tests/test_c3_1_1_mcp_tool_gateway.py` (#12) · probe cases | remove: the probe-shape / probe-fails-at-connect cases go; a wrong shape is now covered by the existing per-call `ToolFailure(unparseable)` map/scrape tests. |
| `config.py` (#2) · `firecrawl_probe_url`; `_decode_body` / `_parse_*` (#5) | check only: kept. The setting and the shape parsers remain; only the connect-time probe step is removed. |

BEFORE
```
McpToolGateway.open()
├─ _start_sessions
├─ verify_capabilities
└─ _probe_firecrawl_shape ──► map_site + scrape_page ──► raise on wrong shape
```

AFTER
```
McpToolGateway.open()
├─ _start_sessions
├─ verify_capabilities
└─ shape probe removed                                 ◄── GONE
     └─ wrong shape (if ever) ──► per-call ToolFailure(unparseable)   ◄── NEW
```

Behaviour change: `open()` spends no map/scrape credits; a wrong output shape, if it ever occurs, surfaces per-call on first real use instead of at connect.

---

## 6. DECISION-GATED points

None. The fix **reverts** the plan's own iteration 4 (A5/M11/A6), but this is not a contradiction the plan left open: the plan's Iteration 4 appendix already flags it (F24 "A5/M11 cannot resolve on the live endpoint"; F25 "iteration 4 is superseded by the pending fan-out fix, not yet coded"). The new spec is the execution of that documented trajectory, so there is nothing to adjudicate. The old plan's "batch tool exists — Trust (confirmed)" assumption is contradicted by live evidence, but it is resolved, not open (see F1).

---

## 7. Unchanged

- The multi-URL op's **parameter and field shapes**: `(urls, *, formats)` in, and `pages` / `total` / `completed` / `failed_urls` / `retrieved_at` out — only the method name (`batch_scrape`→`scrape_pages`) and the type name (`BatchScrapeResult`→`ScrapeResults`) change (see M1), not the shape.
- The singular `scrape_page(url) -> ScrapeResult` operation and its `ScrapeResult` contract, keyed by `metadata.sourceURL`; per-URL failure as a signalled degrade in `failed_urls`.
- `_firecrawl_sem` (`FIRECRAWL_CONCURRENCY = 2`) as the Firecrawl concurrency bound (A7 adds a per-minute bucket *alongside* it; the semaphore itself is unchanged).
- `web_search` (Parallel): its own `_search_sem` (`SEARCH_CONCURRENCY = 4`) and reactive-only rate handling — explicitly **not** touched by A7's Firecrawl-path bucket (different server, different key).
- `firecrawl_map` + `firecrawl_scrape` as the required capabilities (the `tools/list` check; the shape probe is removed — see R3).
- `crawl_site` retained, unused by M3.
- `mcp.tools_listed` [A6] — the general per-server capability-boundary log is kept (only the batch-specific A6 logs go, under R2).

> Note: "batch is out of `verify_capabilities`" is **not** listed here as unchanged. In the as-built (iteration-4) baseline batch **is** in `verify_capabilities` (M11); R2 removes it, so this is a change, not a constant.

---

## 8. Component traceflow after all points

```
caller ──► McpToolGateway.open()
│
├─ verify_capabilities
│    ├─ require web_search / firecrawl_map / firecrawl_scrape
│    └─ batch not referenced                                 ◄── R2
├─ shape probe removed                                       ◄── R3
│
caller ──► McpToolGateway.scrape_pages(urls)                 ◄── M1 (renamed)
├─ gather scrape_page(url) per url                           ◄── M1
│    └─ each ─► _single_call                                 
│         ├─ _firecrawl_sem (≤ 2 in flight)                  
│         └─ rate token (≤ 10 / min, wait if empty)          ◄── A7
├─ return_exceptions=True ──► failed_urls on per-url failure  ◄── M1
├─ job-envelope poll path                                    ◄── R1 (removed)
└─ ──► ScrapeResults(pages keyed by sourceURL, failed_urls)   ◄── M1 (renamed)
```

---

## 9. Flags

| # | Flag |
|---|------|
| F1 | The old plan's build-time note "batch tool existence confirmed by the domain owner — Trust (confirmed)" is contradicted by the live `tools/list`: the hosted `https://mcp.firecrawl.dev/v2/mcp` returns 28 tools, **none** containing `batch`. The `-32601 Unknown tool` was the tool being genuinely absent. |
| F2 | This fix is a **large revert plus a removal** spanning plan-documented work: it reverts all of iteration 4 (A5 resolution, M11 connect requirement, A6 batch logs), removes A4's batch-job mechanism (R1) and A3's probe (R3), and renames + rewrites `batch_scrape`→`scrape_pages` (M1). The plan's own F24/F25 anticipate the revert, but confirm all of it is intended in one pass rather than keeping, say, `mcp.tools_listed` only (it is kept) or the resolver for a future self-hosted batch server (it is not). |
| F3 | Timeout model changes: the per-job `BATCH_DEADLINE_SECONDS = 300` is gone; each fanned-out scrape is bounded by `SCRAPE_TIMEOUT_SECONDS = 60` and the whole call by how long the slowest scrape in the gathered set takes under the 2-slot semaphore. Confirm 60 s per page is the intended ceiling for shortlist scraping. |
| F4 | Tradeoff left open: fan-out is N round trips vs one job clock. Fine at the current 2-browser plan limit and low-tens shortlists. If shortlists grow to hundreds and the Firecrawl plan is upgraded for higher parallelism, a real batch path (self-hosted MCP batch tool or Firecrawl REST `/batch/scrape`) may be worth revisiting; not needed now. |
| F5 | Sample runner (M12): `--batch-only` still runs (it now calls `scrape_pages`, a fan-out), but `--trace-calls`'s batch-scoped tracing filters on the `"batch"` substring in tool names/messages — after the fan-out there are no batch-named MCP calls, so that scoped trace shows nothing. Decide whether to re-scope it to `firecrawl_scrape` and/or rename the `--batch-only` flag (e.g. `--scrape-only`), or leave `--trace-transport` as the only useful trace for this path. |
| F6 | **Rename deviation from the literal request.** You asked for `scrape_page` / `ScrapeResults`. The method was made **`scrape_pages`** (plural) because `scrape_page(url) -> ScrapeResult` already exists as the single-page op the fan-out calls; reusing the singular names would collide. If you intended to overload or replace the single-page op instead, say so and the rename changes. |
| F7 | **A7's limiter bounds only *our* process, and only if the gateway is shared.** The 10/min is per-key / team-wide; a token bucket inside our gateway cannot see a teammate's process on the same key, so the reactive 429 backoff stays as that backstop. And the bucket (like `_firecrawl_sem`) is **gateway-instance** state — it paces all concurrent amenities together only because C3.1.7 shares **one** gateway per run. A gateway-per-amenity would give each its own 10/min → 10×N (the same invariant as the semaphore). That shared-gateway guarantee is a **C3.1.7 handoff**, not built in C3.1.1. |

---

## 10. Updated C3.1.1 spec (lives here for now)

> This is the old C3.1.1 spec with the fix incorporated. Only the batch-related and timeout/concurrency lines change from the old spec; everything else is reproduced unchanged so this stands alone.

### C3.1.1 — Build the MCP Tool Gateway for Parallel and Firecrawl

**Goal.** Typed async operations over the two hosted MCP servers: `search_web(objective, search_queries)` → Parallel `web_search`; and for Firecrawl, `map_site(url)` → `firecrawl_map`, `scrape_page(url)` → `firecrawl_scrape`, and `scrape_pages(urls)` → **a concurrent fan-out of `firecrawl_scrape` over the app-shortlisted URLs** (the hosted server exposes no batch tool) — the M3 uses — with `crawl_site(url, limit, depth)` → `firecrawl_crawl` **retained for future use but unused by M3**. Each returns typed results or a typed failure. Sessions open/close in one async scope. The connect step verifies the expected tools and argument names exist.

**Problem.** R2 has no MCP client (no `mcp` dependency, no server keys). MCP returns generic content blocks, not typed data. A session is stateful and must open/close in the same async task. A server can rename/remove a tool; without a connect-time check, the failure surfaces mid-run.

**Finalized approach.** High-level `Client` wrapper — one `Client(transport)` per server, transport built with `streamable_http_client(url, http_client=...)`. The wrapper owns the session, handshake, and context management, and offers convenience methods. The `httpx2` client carrying the `Authorization` header is created and owned by the gateway. It is built with an explicit `httpx2.Timeout(connect=10, read=None, write=10, pool=10)`: `read=None` leaves the long-lived SSE response stream unbounded at the transport, so the per-call `asyncio.timeout` and SDK `read_timeout_seconds` are the single duration bound.

**Decisions — generally mandatory**
- **Session scope.** Sessions open at the start of `run_llm_metric_resolution` and close at its end, same task. `aclose()` closes a leaked session.
- **Authentication.** Bearer keys from `Settings` (`PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`). Keys never logged.
- **Retry & timeouts.** Retry transient failures only (timeout, transport, rate limit), backing off by kind: timeout/transport 2 s then 3 s; a rate limit waits a window-clearing 30 s then 60 s (or a response `Retry-After`). Per-call timeouts are queue-inclusive: map and scrape 60 s, search 30 s. **`scrape_pages` has no job clock; each fanned-out page uses the 60 s scrape timeout, and the call ends when its gathered scrapes settle.** *(changed)* **Firecrawl calls are also paced proactively to ≤10/min by a token bucket (A7); an over-budget call waits for the window rather than firing and taking a `429`.** *(changed)*
- **Error typing.** `is_error` result → typed tool failure. A dropped SSE stream (`MCPError`, "SSE stream ended / reconnection attempts exhausted") is classified `transport` and retries on the same session; a `429` is classified `rate_limited` even inside an `MCPError`. Connect/protocol failure → MCP error family with `stage`.
- **Test seam.** Gateway is a `Protocol` injected into `AmenitySearch`; a fake stands in for tests.

**Decisions — problem-specific**
- **Capability check.** `tools/list` must contain `web_search` (args `objective`, `search_queries`) on Parallel and **`firecrawl_map` (arg `url`) + `firecrawl_scrape` (args `url`, `formats`)** on Firecrawl. A miss raises `McpToolUnavailableError` before any amenity work. **`firecrawl_crawl` is retained but NOT checked here** — a server missing it still opens, and the gap surfaces as a per-call `ToolFailure` on the first `crawl_site`. **No batch tool is checked or required, because `scrape_pages` calls no MCP batch tool — it fans out `firecrawl_scrape`, which is already required.** *(changed)*
- **Firecrawl map/scrape operations (M3 path).** `map_site(url)` calls `firecrawl_map` and returns the site's link set; `scrape_page(url)` calls `firecrawl_scrape` (`formats: ["markdown"]`, `onlyMainContent`) and returns one typed page. **`scrape_pages(urls)` scrapes the app-shortlisted URLs by running one `scrape_page` per URL concurrently, each bounded by the shared Firecrawl semaphore (`FIRECRAWL_CONCURRENCY = 2`), gathering outcomes so one failed URL does not fail the rest.** The LLM never supplies a URL (C3.1.3). `scrape_page` is also used for single-page work. *(changed)*
  - *multi-page output shape.* **`scrape_pages` returns a `ScrapeResults` whose `pages` are the successful `ScrapeResult`s (one per URL, keyed by `metadata.sourceURL`), with `total`/`completed` counts and the URLs that failed in `failed_urls` (a signalled degrade, logged, not a whole-call failure). There is no job envelope, status polling, or pagination cursor.** *(changed)*
- **Result parsing — map/scrape** (verified against the server source; both decode via `_decode_body`): *scrape* reads top-level `markdown` + `metadata.sourceURL`; *map* reads the `links` array of `{url, title?, description?}` (tolerating an older plain-string form). A scrape with no non-empty `sourceURL` is a failure (evidence is keyed by URL). *(unchanged)*
- **MCP result wrapping & `structuredContent` decode.** Both servers return the payload twice (`content[].text` JSON and a native `structured_content`); `_decode_body` prefers the structured object, then JSON-decodes the text block. *(unchanged)*
- **Firecrawl output shape.** M3 requires MCP server 3.x JSON output (top-level `markdown` + `metadata.sourceURL`; a `links` list for map). **A live run confirmed the hosted `/v2` server returns this shape, so the connect-time probe is removed; `open()` runs the `tools/list` capability check only.** A wrong shape, if it ever occurs, surfaces as a per-call `ToolFailure(unparseable)` on the first real map/scrape. The `FIRECRAWL_PROBE_URL` setting and the `_decode_body` / `_parse_*` handling are kept. *(changed)*
- **Parallel `web_search` result.** `results[]` with `url`, `title`, `excerpts` (list of strings); existing parser handles it. *(unchanged)*
- **Crawl result shape / read timeout (retained crawl path, not used by M3).** Handle both final-data and job-id-poll shapes via `firecrawl_check_crawl_status`; a timed-out crawl is re-read by id, not restarted. *(unchanged)*
- **Concurrent calls on one Client.** One `Client` per server, shared across amenity pipelines in one event loop; concurrency capped by a per-server semaphore; every call has an explicit timeout; the session is never replaced — a transient failure (incl. dropped SSE) retries by reissuing the call on the same `Client`. **`scrape_pages`'s fan-out shares the same `_firecrawl_sem`, so it never exceeds the 2-browser limit or self-induces a `429`.** *(changed)*
- **Rate limits & concurrency.** Firecrawl is bounded on **two axes**, both as shared gateway state so one gateway paces all concurrent amenities, and **both applied to every Firecrawl call** (`firecrawl_map`, `firecrawl_scrape`, `firecrawl_crawl`): **concurrency** `FIRECRAWL_CONCURRENCY = 2` (plan browser limit, `_firecrawl_sem`) **and throughput** `FIRECRAWL_RATE_PER_MINUTE = 10` (Free-plan limit, documented for `/scrape`, shared across the team's keys — one proactive token bucket for the whole Firecrawl path, A7). A Firecrawl call takes a slot *and* a token in `_single_call`; over either limit it waits (queues on the slot / sleeps until the window refills), never dropped — so a `map_site` and a `scrape_pages` burst share and contend for the same 10/min. The former batch per-job `maxConcurrency` is gone. Parallel `web_search` is separate: `SEARCH_CONCURRENCY = 4`, no proactive per-minute bucket (reactive `429` handling only). The reactive 429 backoff stays as the backstop for the cross-process slice the in-process bucket cannot see. *(changed)*
- **Verification.**
  - *V2a Parallel:* ~10 concurrent `web_search` calls on one `Client`; each result matches its request; one timeout doesn't fail the others.
  - *V2b Firecrawl (M3 path):* several concurrent `scrape_page` calls on one `Client` after a `map_site`; each result matches its page; one scrape timeout doesn't fail the others; the session stays usable. **`scrape_pages` is covered by the same fan-out path.** *(changed)*

---

# Appendix: Iteration 4 (as built — verified against `mcp_tools.py`)

Iteration 4 was added after the iteration-3 body above and **is in the code now**. It completes OV-11 and
reverses the iteration-2/3 decision to keep batch out of the capability check. The A4 batch-job mechanism
(`batch_scrape` → start → `_read_batch_job` poll → `BatchScrapeResult`) is **unchanged** by iteration 4;
A5/M11 only change how the batch tool *name* is obtained and whether it is required at connect. IDs continue
the plan's space: **A5, A6** (ADD), **M11, M12** (MODIFY), flags **F24+**.

Verified in `mcp_tools.py`: `ResolvedBatchTools` (class), `_resolve_firecrawl_batch_tools`, `_match_batch_tool`,
the `FIRECRAWL_BATCH_*_CANDIDATES` / `FIRECRAWL_BATCH_START_ARGS` constants (replacing the removed fixed
`FIRECRAWL_BATCH_SCRAPE_TOOL` / `_STATUS_TOOL` / `_JOB_ARG` / `_CURSOR_ARG`), `self._batch_tools` set in
`verify_capabilities`, the `_batch_identity` guard, and the five diagnostic events.

## A5: Resolve batch tool names/args from the live `tools/list`

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `ResolvedBatchTools` (frozen dataclass) | add: carries `start_tool`, `status_tool`, `job_id_arg`, `cursor_arg` resolved from the catalog to the call sites. |
| `mcp_tools.py` (#5) · `_resolve_firecrawl_batch_tools`, `_match_batch_tool` | add: match the start/status names (ordered candidates, then a single-match substring fallback with `require`/`include_any`/`exclude`), confirm the start tool exposes `urls`/`formats`, and resolve the job-id/cursor args from the status tool's schema. |
| `mcp_tools.py` (#5) · batch candidate constants | add: `FIRECRAWL_BATCH_SCRAPE_NAME_CANDIDATES`, `FIRECRAWL_BATCH_STATUS_NAME_CANDIDATES`, `FIRECRAWL_BATCH_START_ARGS`, `FIRECRAWL_BATCH_JOB_ARG_CANDIDATES`, `FIRECRAWL_BATCH_CURSOR_ARG_CANDIDATES`; the fixed `FIRECRAWL_BATCH_SCRAPE_TOOL` / `_STATUS_TOOL` / `_JOB_ARG` / `_CURSOR_ARG` are removed. |
| `mcp_tools.py` (#5) · `batch_scrape`, `_read_batch_job` | modify: call `self._batch_identity().start_tool` / `.status_tool` / `.job_id_arg` / `.cursor_arg` instead of the fixed constants; a missing job-id arg degrades to the first candidate (WARN), a missing cursor arg means single-page (WARN on real truncation). |

BEFORE
```
batch_scrape / _read_batch_job
└─ call FIRECRAWL_BATCH_SCRAPE_TOOL / _STATUS_TOOL (fixed constants)
```

AFTER
```
verify_capabilities
└─ _resolve_firecrawl_batch_tools(firecrawl catalog)        ◄── NEW
     ├─ match start/status names (candidates → substring)   ◄── NEW
     ├─ resolve job-id / cursor args from status schema      ◄── NEW
     └─ ──► ResolvedBatchTools stored on self._batch_tools    ◄── NEW
batch_scrape / _read_batch_job
└─ call self._batch_tools.start_tool / .status_tool          ◄── CHANGED
```

Behaviour change: the batch tool name/args come from the live catalog, not a guessed constant.

## M11: `verify_capabilities` resolves and requires the batch tools at connect

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `verify_capabilities` | modify: after requiring `web_search`/`firecrawl_map`/`firecrawl_scrape`, call `_resolve_firecrawl_batch_tools` and store the result; an unresolvable start or status **name** raises `McpToolUnavailableError(stage="verify_capabilities")`. |
| `mcp_tools.py` (#5) · `__init__`, `_batch_identity` | add: `self._batch_tools: ResolvedBatchTools \| None = None`; `_batch_identity()` returns it or raises `McpConnectionError` if batch is used before `open()`. |
| `tests` (#9, #12) | modify: "missing batch tool" now asserts a connect-time raise; resolver unit tests `t62`-`t66` added. |

BEFORE
```
verify_capabilities
├─ require web_search / firecrawl_map / firecrawl_scrape
└─ batch not checked ──► per-call ToolFailure if absent
```

AFTER
```
verify_capabilities
├─ require web_search / firecrawl_map / firecrawl_scrape
└─ resolve + require batch (A5)                              ◄── CHANGED
     └─ unresolvable name ──► McpToolUnavailableError         ◄── CHANGED
```

Behaviour change: a server without a resolvable batch tool fails at connect instead of on first `batch_scrape`.

## A6: Connect/resolution diagnostics

| Artifact | Change |
|---|---|
| `mcp_tools.py` (#5) · `_list_tools` | add: `mcp.tools_listed` INFO per server — `tool_count`, `tools`, and per-tool `args` (the full catalog, a boundary crossing). |
| `mcp_tools.py` (#5) · `_resolve_firecrawl_batch_tools` | add: `mcp.batch_tools_resolved` INFO (resolved identity), `mcp.batch_arg_unresolved` WARN (job-id arg fell back to default), `mcp.batch_resolution_failed` WARN (names unresolved — dumps candidates + catalog) before the raise. |
| `mcp_tools.py` (#5) · `_read_batch_job` | add: `mcp.batch_pages_truncated` WARN when the job pages further but no cursor arg exists (degrade). |

Behaviour change: a connect run records exactly which tools the servers expose and why batch resolution succeeded or failed, without re-running.

## M12: Sample runner — `--batch-only` and scoped tracing

| Artifact | Change |
|---|---|
| `mcp_tool_gateway_sample_run.py` (#10) · `--batch-only`, `_stage_open_batch_only`, `_is_batch_tool` | add: connect via `_start_sessions` + `verify_capabilities` (no probe) and run only `batch_scrape([site_url])`, so the working tools spend no credits. |
| `mcp_tool_gateway_sample_run.py` (#10) · `--trace-transport`; `--trace-calls` scoping | modify: `--trace-calls` now scopes the call + transport tracers to batch tools only; the full whole-run SDK/httpx relays move behind the new `--trace-transport`. |

Behaviour change: a batch-focused run is readable (working stages quiet) and cheap (only the batch call bills).

## Iteration 4 flags

| # | Flag |
|---|------|
| F24 | **A5/M11 cannot resolve on the live endpoint.** A `--batch-only` run showed the hosted `/v2` server lists 28 tools, **none** a batch tool. The `-32601 Unknown tool` was the tool being absent, contradicting OV-11's "existence confirmed by the domain owner." |
| F25 | **Iteration 4 is superseded by the pending fan-out fix (not yet coded).** The agreed fix (in `deep_search_context.md` and `..._iteration4_report.md`) reverts A5/M11, **renames `batch_scrape`→`scrape_pages` and `BatchScrapeResult`→`ScrapeResults`** and reimplements it as a concurrent `scrape_page` fan-out, removes the connect-time probe, and **adds the A7 proactive Firecrawl rate limiter (≤10/min token bucket + existing ≤2 `_firecrawl_sem`)**. This plan documents iteration 4 as built; the next plan revision will fold in that fix. |
| F26 | **A7 limiter is C3.1.1-scoped but depends on a C3.1.7 invariant.** The ≤10/min bucket is gateway-**instance** state, so it paces all concurrent amenities together **only if C3.1.7 shares one gateway per run** (a gateway-per-amenity → 10×N). That shared-gateway guarantee is a C3.1.7 handoff. Cross-process/team-wide enforcement (another process on the same key) is out of scope; the reactive 429 backoff is its backstop. |
