# Test Plan — R2 Mechanism 3, Sub-component C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl)

**Status: tests written, run, and mutation-verified.** The six-field entries below are the plan; the
to-do list and the verification record at the bottom show what was done after it.

**Resource under test:** `src/clients/mcp_tools.py` — `McpToolGateway`, its `_ServerSession` owner
tasks, the module-level parsers/classifier reached through the public methods, and the
`create_mcp_tool_gateway` composition root. Implementation spec:
`feature_context/deep_search_context.md` (C3.1.1) and
`feature_context/r2_mechanism_3_c3_1_1_implementation_plan.md`. Manual counterpart:
`feature_sample_runs/mcp_tool_gateway_sample_run.py` (live, spends credits; not duplicated here).

**Tests:** `test_c3_1_1_mcp_tool_gateway.py` (same folder), 49 test functions / 76 collected cases,
ids `T1..T49` matching the entries below.

**Run (from `backend/`):**
`python -m pytest src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py -q`

> This plan replaces the earlier C3.1.1 plan, which targeted the pre-map/scrape gateway (crawl as the
> M3 path, `firecrawl_crawl` required at connect). That is no longer the contract: M3 drives
> `search_web` / `map_site` / `scrape_page`, the crawl path is retained but not required, and open()
> runs a Firecrawl shape probe (MCP server 3.x JSON output).

---

## Guiding decision for real-vs-mock (applies to the whole plan)

> Test the decisions the gateway makes, at a boundary where the outcome is observable, using real
> dependencies for what can actually be wrong (our retry/poll/parse/lifecycle/concurrency logic, the
> real `mcp.Client`, the real in-process MCP transport) and fakes only for what is costly or outside
> the system (the hosted Parallel/Firecrawl servers, wall-clock backoff).

**REAL in every entry:** the full `McpToolGateway`, `_ServerSession` owner tasks, per-server
semaphores, the real `mcp.Client`, the MCP protocol, and the parsers/classifier reached via the
public methods. T48–T49 additionally use the **production** `_streamable_http_factory`, `httpx2`, and
real loopback HTTP (uvicorn), because every other test injects its own client factory and would
otherwise never execute the production factory or the bearer header.

**FAKED, and why that is legitimate:**
- **The hosted MCP servers** → in-process `MCPServer`s with configurable async tool handlers, injected
  through the gateway's own `client_factory` seam. The vendor is outside the system, costs money, and
  is non-deterministic; the gateway still speaks real MCP to it.
- **`mcp_tools._async_sleep`** → monkeypatched (recorded and instant, gated on an `Event`, or a real
  10 ms) so backoff/poll values are asserted without waiting. Real `asyncio.timeout` budgets are
  shrunk where a genuine timeout must fire.
- **A flaky client wrapper** (T23, T24) → raises `ConnectionError`/`httpx2.ConnectError` from
  `call_tool`, the one edge an in-process server cannot produce. Only `call_tool` is wrapped.
- **Synthetic exception objects** (T27 only) → unit test of `_classify_failure`; justified in T27.

**Not tested (skill's "do not test" list):** the `mcp` SDK's own connect/serve mechanics, dataclass
construction/immutability, `Settings` env loading, the trivial `_timestamp` helper, and the live
sample runner's V2a/V2b checks (live vendors; stay manual).

**Type labels:** `integration` = through the public gateway against the in-process vendor, no
network; `unit` = a pure function in isolation; `e2e` = composition root + production factory over
real loopback HTTP.

---

## 1. Capability check (`open` → `verify_capabilities`)

### T1 — `test_t1_open_succeeds_when_required_tools_and_args_are_present`
1. **Target:** `McpToolGateway.open` / `aclose`.
2. **Core behavior:** `open` starts one session per server and returns only when every required tool
   and argument is present; the sessions stay open until `aclose`.
3. **Behavior under test:** complete catalogs → `open` returns, exactly one client per server was
   built, and `aclose` releases both.
4. **Type:** integration.
5. **Real vs mocked:** real gateway/client; in-process servers with the required tools; factory
   records open/close events.
6. **Evidence:** asserts the open/close event pairs (one each per server), not just "no exception" —
   a gateway that built extra clients, or never released one, fails.

### T2 — `test_t2_missing_required_tool_or_argument_fails_at_connect` (4 cases)
1. **Target:** `verify_capabilities` / `_require`.
2. **Core behavior:** a missing required tool or argument fails fast at connect, not mid-run.
3. **Behavior under test:** each of {Parallel `search_queries` arg, `firecrawl_map`,
   `firecrawl_scrape`, scrape `formats` arg} absent → `McpToolUnavailableError`,
   `stage == "verify_capabilities"`, message names the missing item, and no session task is left.
4. **Type:** integration.
5. **Real vs mocked:** real gateway; in-process servers each built without exactly one requirement.
6. **Evidence:** each case differs from T1 by one removed requirement, and the message must contain
   that requirement's name — so a check that skipped any one line, or raised for the wrong reason,
   fails exactly that case.

### T3 — `test_t3_crawl_tools_are_not_required_and_fail_per_call`
1. **Target:** `verify_capabilities` (crawl/status intentionally unchecked) + `crawl_site`.
2. **Core behavior:** M3 does not drive crawl, so a server without crawl/status still connects; the
   gap is a per-call `ToolFailure`.
3. **Behavior under test:** Firecrawl lacking both crawl tools → `open` passes; `crawl_site` returns
   `ToolFailure(tool="firecrawl_crawl")`, not a raise.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; Firecrawl built without crawl/status.
6. **Evidence:** pins the deliberate "retained but not required" decision (a regression that
   re-added the requirement would break every map/scrape-only server).

---

## 2. Firecrawl shape probe (`open` → `_probe_firecrawl_shape`)

> **Retired in iteration 5 (R4).** The connect-time probe was removed; `open()` runs the capability
> check only. Tests T4–T6 are deleted. A wrong output shape now surfaces per-call as
> `ToolFailure(unparseable)`, covered by the map/scrape parse cases (T13–T19). See the Iteration 5
> update at the end of this file.

### T4 — `test_t4_probe_maps_and_scrapes_the_configured_url_after_the_capability_check`
1. **Target:** `open` ordering + probe.
2. **Core behavior:** after the capability check, one `firecrawl_map` and one `firecrawl_scrape` of
   the configured probe URL confirm the MCP server 3.x JSON output shape.
3. **Behavior under test:** capabilities run first; then exactly one map and one scrape hit the
   configured URL (not the default).
4. **Type:** integration. 5. **Real vs mocked:** real gateway; handlers record `map:`/`scrape:` +
   URL; `verify_capabilities` wrapped to log its position.
6. **Evidence:** the event order and the exact URLs are the observable proof the probe ran, on the
   right page, after the check — a skipped or mis-sequenced probe changes the list.

### T5 — `test_t5_probe_rejects_a_non_v3_shape_and_leaves_no_task` (5 cases)
1. **Target:** `_probe_firecrawl_shape`.
2. **Core behavior:** a Firecrawl shape other than the 3.x JSON output raises before any amenity
   work, with nothing leaked.
3. **Behavior under test:** {blank `sourceURL`, no `metadata`, wrapped `data` envelope, blank page
   text, map without `links`} → `McpToolUnavailableError`, `stage == "verify_probe"`, and no
   `mcp-session-*` task remains.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; Firecrawl serving the bad body for
   every URL (so the probe, not a later call, sees it).
6. **Evidence:** the wrapped-envelope and blank-text cases are exactly what an older Firecrawl
   returns; the before/after task set proves the teardown, which "it raises" alone would miss.

### T6 — `test_t6_probe_that_cannot_complete_is_a_connection_error_not_a_shape_error`
1. **Target:** `_probe_firecrawl_shape` (transient vs shape split).
2. **Core behavior:** a probe call that could not complete is `McpConnectionError`, not
   `McpToolUnavailableError` — "unreachable" must not be reported as "wrong version".
3. **Behavior under test:** a persistently rate-limited probe scrape → `McpConnectionError`,
   `stage == "verify_probe"`, not a `McpToolUnavailableError`, after the normal backoffs `[2.0, 3.0]`.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; scrape tool always rate-limited;
   `_async_sleep` recorded.
6. **Evidence:** the exception *type* distinction drives operator action; the recorded backoffs show
   the probe used the shared retry rather than failing on the first transient blip.

---

## 3. `search_web` and its parser

### T7 — `test_t7_search_parses_the_documented_parallel_shape_and_echoes_the_request`
1. **Target:** `search_web` + `_parse_search_result` / `_excerpt_text`.
2. **Core behavior:** a Parallel body (`results[]` with `url`, `title`, `excerpts` as a list of
   strings) becomes typed `SearchExcerpt`s; the result echoes the request and is time-stamped.
3. **Behavior under test:** two hits (one with a `None` title) parse to the exact
   `(url, title, text)` tuples with excerpt strings joined by newline; `objective`/`search_queries`
   echo the request; `retrieved_at` is set.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; Parallel server returns the body.
6. **Evidence:** expected values are written independently of the implementation (the join rule and
   the `None` title), so a parser that kept only the first excerpt or dropped untitled hits fails.

### T8 — `test_t8_search_prefers_structured_content_over_the_text_block`
1. **Target:** `_decode_body`.
2. **Core behavior:** structured content is read first; the JSON text block is the fallback.
3. **Behavior under test:** a result whose text block and `structured_content` disagree is parsed
   from the structured payload.
4. **Type:** integration. 5. **Real vs mocked:** tool returns a `CallToolResult` with differing
   payloads, through the real client.
6. **Evidence:** the two payloads carry different URLs, so only the preferred source can satisfy the
   assertion — the preference is observed, not assumed.

### T9 — `test_t9_empty_search_hit_list_is_a_valid_result_not_a_failure`
1. **Target:** `_parse_search_result` (zero-hit boundary).
2. **Core behavior:** zero hits is a valid `WebSearchResult`, never a failure.
3. **Behavior under test:** `{"results": []}` → `WebSearchResult` with `excerpts == ()`.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; Parallel returns an empty list.
6. **Evidence:** "no data" being turned into an error is the classic boundary bug; asserting the
   typed result (not a `ToolFailure`) pins the documented rule.

### T10 — `test_t10_unreadable_search_body_is_unparseable_not_an_empty_result` (4 cases)
1. **Target:** `_parse_search_result` (de-mask).
2. **Core behavior:** an unreadable body is `ToolFailure(unparseable)`, never a confident empty result.
3. **Behavior under test:** {dict with no hit-list key, hits not a list, a hit that is not an object,
   non-JSON text} → `ToolFailure(tool="web_search", kind="unparseable")`.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; Parallel returns the bad body.
6. **Evidence:** the first case is the dangerous one — it would look like "zero results" and hide a
   real shape drift; asserting `unparseable` proves the mismatch is surfaced.

---

## 4. `map_site` and its parser

### T11 — `test_t11_map_returns_every_link_unfiltered_uncapped_and_in_order`
1. **Target:** `map_site` / `_parse_map_result`.
2. **Core behavior:** returns the site's link set as typed candidates; filtering and capping belong to
   the caller (C3.1.6), not the gateway.
3. **Behavior under test:** 60 links plus one off-host link → all 61 returned, in order, with
   `title`/`description` carried; `url` and `retrieved_at` set.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; Firecrawl map returns the links
   (probe URL answered separately).
6. **Evidence:** a count above any plausible cap and an off-host entry make a hidden host filter or
   truncation observable; order and field values are asserted per link.

### T12 — `test_t12_map_tolerates_plain_string_links`
1. **Target:** `_parse_map_result` (legacy shape). 2. **Core behavior:** older servers return bare
   URL strings; they are accepted. 3. **Behavior under test:** `links: ["…/a","…/b"]` → two `MapLink`s
   with `title is None`. 4. **Type:** integration. 5. **Real vs mocked:** real gateway; string-link
   body. 6. **Evidence:** exact URLs and `None` titles distinguish "tolerated" from "dropped".

### T13 — `test_t13_empty_map_is_a_valid_result`
1. **Target:** `_parse_map_result` (zero boundary). 2. **Core behavior:** a genuinely empty site is a
   valid result. 3. **Behavior under test:** `{"links": []}` → `MapResult(links=())`. 4. **Type:**
   integration. 5. **Real vs mocked:** real gateway. 6. **Evidence:** pairs with T15 — empty list is
   valid, missing list is not; together they prove the parser distinguishes the two.

### T14 — `test_t14_map_drops_malformed_entries_and_records_how_many`
1. **Target:** `_parse_map_result` (degrade + log). 2. **Core behavior:** unusable entries are
   skipped and the only evidence is a warn line with counts. 3. **Behavior under test:** `[ok,
   {title only}, 5, "  "]` → one link kept; one `mcp.map_links_skipped` record with
   `skipped == 3`, `kept == 1`. 4. **Type:** integration. 5. **Real vs mocked:** real gateway;
   `caplog`. 6. **Evidence:** a degrade raises nothing, so the log record is the sole observable
   proof candidates were dropped; the exact counts catch a silent or mis-counted skip.

### T15 — `test_t15_unreadable_map_body_is_unparseable` (3 cases)
1. **Target:** `_parse_map_result` (de-mask). 2. **Core behavior:** a body with no `links` list, a
   non-list `links`, or a non-empty list with no usable entry is a shape error, not an empty site.
3. **Behavior under test:** each → `ToolFailure(tool="firecrawl_map", kind="unparseable")`.
4. **Type:** integration. 5. **Real vs mocked:** real gateway. 6. **Evidence:** the "no usable
   entry" case is the one an `if not links` shortcut would misreport as empty.

---

## 5. `scrape_page` and its parser

### T16 — `test_t16_scrape_is_keyed_by_the_server_reported_source_url`
1. **Target:** `scrape_page` / `_parse_scrape_result`. 2. **Core behavior:** `ScrapeResult.url` is
   `metadata.sourceURL`, because M3 keys evidence by the page the server actually returned.
3. **Behavior under test:** request `…/start`, server reports `…/final` → result `url` is `…/final`,
   `text` is the markdown. 4. **Type:** integration. 5. **Real vs mocked:** real gateway.
6. **Evidence:** request and reported URL differ, so echoing the request fails.

### T17 — `test_t17_scrape_requests_markdown_of_the_main_content_only`
1. **Target:** `scrape_page` argument construction. 2. **Core behavior:** always asks for
   `formats=["markdown"]` and `onlyMainContent=true`. 3. **Behavior under test:** the arguments the
   Firecrawl tool receives. 4. **Type:** integration. 5. **Real vs mocked:** tool handler captures
   its arguments. 6. **Evidence:** the interaction *is* the behavior here (what is sent to a paid
   vendor, and what shape comes back); a wrong format would change the response shape the parser
   depends on.

### T18 — `test_t18_empty_markdown_with_a_source_url_is_a_valid_page`
1. **Target:** `_parse_scrape_result` (boundary). 2. **Core behavior:** blank page text with a source
   URL is a valid page. 3. **Behavior under test:** `markdown == ""` → `ScrapeResult(text="")`.
4. **Type:** integration. 5. **Real vs mocked:** real gateway. 6. **Evidence:** contrasts with T19:
   empty text is fine, missing URL is not.

### T19 — `test_t19_scrape_without_text_or_source_url_is_unparseable` (5 cases)
1. **Target:** `_parse_scrape_result`. 2. **Core behavior:** a page that cannot be keyed or has no
   text field is unusable; no older-shape tolerance exists. 3. **Behavior under test:** {blank
   `sourceURL`, no `metadata`, no `markdown`, wrapped `data` envelope, non-JSON text} →
   `ToolFailure(tool="firecrawl_scrape", kind="unparseable")`. 4. **Type:** integration.
   5. **Real vs mocked:** real gateway. 6. **Evidence:** the wrapped envelope is the real v1/v2
   shape; accepting it would silently produce evidence with no URL provenance.

---

## 6. Failure typing and retry policy (`_single_call`, `_call_with_retry`)

### T20 — `test_t20_tool_error_is_returned_not_raised_and_not_retried`
1. **Target:** `search_web` → `_single_call`/`_classify_failure`. 2. **Core behavior:** a non-transient
   tool error is returned as a `ToolFailure` and attempted once. 3. **Behavior under test:** a
   generic `ToolError` → `ToolFailure(web_search, tool_error)`, message carries the server's reason,
   one call, no backoff. 4. **Type:** integration. 5. **Real vs mocked:** real gateway; counting
   handler; `_async_sleep` recorded. 6. **Evidence:** attempt count 1 and an empty sleep log prove
   the retry gate discriminates by kind; an exception would surface as a test error.

### T21 — `test_t21_rate_limit_retries_twice_with_backoffs_then_fails` (search / map / scrape)
1. **Target:** `_call_with_retry` via each M3 operation. 2. **Core behavior:** transient failures
   retry twice with 2 s then 3 s; exhaustion returns the failure. 3. **Behavior under test:** a
   persistently rate-limited tool is called exactly 3 times, backoffs `[2.0, 3.0]`, final
   `ToolFailure(rate_limited)`. 4. **Type:** integration. 5. **Real vs mocked:** real gateway;
   counting handler; recorded sleep. 6. **Evidence:** attempt count and recorded sleeps come from the
   control flow, not from re-reading the constants; each operation passes its own `retry_kinds`, so
   parametrizing catches a per-operation omission.

### T22 — `test_t22_a_transient_failure_that_clears_returns_the_typed_result`
1. **Target:** `_call_with_retry` (recovery path). 2. **Core behavior:** a retry that succeeds
   returns the normal typed result. 3. **Behavior under test:** first call rate-limited, second
   succeeds → `WebSearchResult`, 2 calls, one 2.0 s backoff. 4. **Type:** integration.
5. **Real vs mocked:** real gateway; handler fails once. 6. **Evidence:** every other retry test
   ends in failure; this is the only proof retry *recovers* rather than merely repeats.

### T23 — `test_t23_transport_errors_are_retried_and_recover`
1. **Target:** `_single_call`/`_classify_failure` transport branch. 2. **Core behavior:** link-level
   errors (`ConnectionError`, `httpx2.ConnectError`) are transient and retried. 3. **Behavior under
   test:** two transport errors then a good response → `WebSearchResult`, backoffs `[2.0, 3.0]`.
4. **Type:** integration. 5. **Real vs mocked:** `_FlakyClient` raises from `call_tool` (the network
   edge); everything else real. 6. **Evidence:** reaches the transport branch through the public
   method, which an in-process tool error cannot.

### T24 — `test_t24_persistent_transport_error_returns_a_transport_failure`
1. **Target:** same, exhaustion. 2. **Core behavior:** exhausted transport errors return
   `ToolFailure(transport)`, not a raise. 3. **Behavior under test:** three `ConnectionError`s →
   `ToolFailure(web_search, transport)`, backoffs `[2.0, 3.0]`. 4. **Type:** integration.
   5. **Real vs mocked:** as T23. 6. **Evidence:** the kind is what lets the caller see a dead session
   as repeated `transport` failures instead of an exception mid-gather.

### T25 — `test_t25_timeout_is_retried_then_reported_and_the_session_is_reused` (search / map / scrape)
1. **Target:** `_single_call` timeout + the "never replace a Client" decision. 2. **Core behavior:**
   a timeout is our side giving up on one wait; it is retried, reported as `timeout`, and the open
   session serves the next call. 3. **Behavior under test:** a slow handler → 3 attempts,
   `ToolFailure(timeout)`, backoffs `[2.0, 3.0]`; a following fast call succeeds; each server's
   client was opened exactly once. 4. **Type:** integration. 5. **Real vs mocked:** real
   `asyncio.timeout` with shrunk budgets; factory open-event counter. 6. **Evidence:** the factory
   open count is the decisive proof no client was rebuilt; the successful follow-up proves the
   session survived.

### T26 — `test_t26_every_failed_attempt_is_logged_with_its_index_and_page`
1. **Target:** `_log_attempt`. 2. **Core behavior:** each failed attempt is a WARN record the
   operator can read, tied to its page. 3. **Behavior under test:** a rate-limited scrape logs
   `mcp.call_attempt_failed` with attempts 0, 1, 2, kind `rate_limited`, and `target` = the page.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; `caplog`. 6. **Evidence:** retried
   failures raise nothing, so these records are the only trail; indices and target are asserted.

### T27 — `test_t27_classifier_maps_exception_types_to_failure_kinds` (7 cases)
1. **Target:** `_classify_failure` (pure). 2. **Core behavior:** maps an exception to a kind:
   transport types → `transport`, timeout → `timeout`, 429/"too many requests" → `rate_limited`,
   else `tool_error`. 3. **Behavior under test:** the seven representative inputs map as listed.
4. **Type:** unit. 5. **Real vs mocked:** real function, synthetic exceptions. **Justification for
   testing a private helper:** HTTP-429 status objects and the `OSError` family cannot be produced
   by the in-process server, yet a wrong kind decides whether a recoverable call is retried.
6. **Evidence:** each input's only salient property is its type/status/text, so the assertion
   isolates the rule.

---

## 7. Input validation and the pre-open guard

### T28 — `test_t28_invalid_arguments_raise_value_error_before_any_tool_call` (10 inputs)
1. **Target:** argument guards of `search_web`, `map_site`, `scrape_page`, `crawl_site`.
2. **Core behavior:** programmer errors raise `ValueError` up front and never spend a call.
3. **Behavior under test:** blank objective, no/blank queries, non-http(s) map/scrape/crawl URLs,
   `limit < 1`, `depth < 0` each raise `ValueError`, and the vendor tool log is unchanged from the
   post-probe baseline. 4. **Type:** integration. 5. **Real vs mocked:** real gateway; recording
   handlers on every tool. 6. **Evidence:** the unchanged call log proves rejection happened *before*
   the vendor (a guard after the call would still raise but would have spent credits).

### T29 — `test_t29_call_before_open_raises_connection_error`
1. **Target:** `_ServerSession.client`. 2. **Core behavior:** no session before `open`; calling is a
   typed error. 3. **Behavior under test:** search/map/scrape on an unopened gateway raise
   `McpConnectionError`. 4. **Type:** integration. 5. **Real vs mocked:** real gateway, never opened.
6. **Evidence:** a typed error (handleable) rather than an `AttributeError` on `None`.

---

## 8. Retained crawl path (`crawl_site`, `_read_crawl_job`)

### T30 — `test_t30_crawl_sends_app_controlled_arguments`
1. **Target:** `crawl_site` arguments. 2. **Core behavior:** crawl scope is set by the app:
   `limit`, `maxDiscoveryDepth`, `allowExternalLinks=false`. 3. **Behavior under test:** the tool
   receives `limit=5`, `depth=2`, `allow_external is False`. 4. **Type:** integration.
5. **Real vs mocked:** argument-capturing handler. 6. **Evidence:** the interaction is the behavior;
   a wrong key or `allowExternalLinks=true` changes scope and cost in production.

### T31 — `test_t31_crawl_accepts_inline_pages_without_polling`
1. **Target:** `_parse_crawl_result` inline shape. 2. **Core behavior:** completed pages in the start
   response are returned without polling. 3. **Behavior under test:** pages parse to
   `(url, title, text)`; status tool call count is 0. 4. **Type:** integration. 5. **Real vs
   mocked:** counting status handler. 6. **Evidence:** page content from the body plus zero polls
   proves this branch, distinct from T32.

### T32 — `test_t32_crawl_polls_a_job_id_to_completion`
1. **Target:** `_read_crawl_job` / `_parse_crawl_status`. 2. **Core behavior:** a job id is polled on
   the same client until complete, waiting the poll interval between reads. 3. **Behavior under
   test:** two "scraping" then complete → `CrawlResult(job_id="job-9")`, status called 3× with the
   same id, two recorded poll waits. 4. **Type:** integration. 5. **Real vs mocked:** stepping
   status handler; `_async_sleep` recorded. 6. **Evidence:** the id sequence and wait count show the
   loop advanced state rather than returning the first response.

### T33 — `test_t33_timed_out_crawl_start_is_never_reissued`
1. **Target:** `crawl_site` start retry policy. 2. **Core behavior:** a start that timed out may
   already be a billed job, so only a rate-limited start retries. 3. **Behavior under test:** start
   exceeds its timeout → `ToolFailure(firecrawl_crawl, timeout)`, start handler called once, no
   backoffs. 4. **Type:** integration. 5. **Real vs mocked:** real `asyncio.timeout`; counting
   handler. 6. **Evidence:** must-not-double-bill is an interaction; `calls == 1` is the right
   non-tautological check.

### T34 — `test_t34_timed_out_status_read_is_asked_again_with_the_same_id`
1. **Target:** `_read_crawl_job` timeout recovery. 2. **Core behavior:** a timed-out status read is
   our wait giving up, so the same job id is asked again; the crawl is not restarted.
3. **Behavior under test:** first status read times out → result is a `CrawlResult`; crawl start
   called once; status ids `["job-t", "job-t"]`. 4. **Type:** integration. 5. **Real vs mocked:** as
   T33. 6. **Evidence:** the id list and start count separate "re-read" from "restart".

### T35 — `test_t35_crawl_deadline_returns_a_timeout_that_carries_the_job_id`
1. **Target:** `_read_crawl_job` deadline. 2. **Core behavior:** a stuck job ends at the overall
   deadline with a timeout that keeps the job id. 3. **Behavior under test:** status always
   "scraping" past a shortened deadline → `ToolFailure(check_crawl_status, timeout)` with
   `"job-stuck"` in the message. 4. **Type:** integration. 5. **Real vs mocked:**
   `CRAWL_DEADLINE_SECONDS` shrunk; 10 ms real poll wait. 6. **Evidence:** both the typed failure and
   the preserved handle are asserted.

### T36 — `test_t36_unrecognised_status_fails_at_once_instead_of_polling_to_the_deadline`
1. **Target:** `_parse_crawl_status` (de-mask). 2. **Core behavior:** an unknown status word with no
   pages is a shape problem and must not be mislabelled a timeout. 3. **Behavior under test:**
   status `"banana"` → `ToolFailure(unparseable)` after exactly one status call. 4. **Type:**
   integration. 5. **Real vs mocked:** real gateway; counting handler. 6. **Evidence:** the call
   count of 1 proves it failed immediately rather than polling for 180 s.

---

## 9. Session lifecycle (`_ServerSession`, `open`, `aclose`)

### T37 — `test_t37_aclose_is_idempotent_and_releases_every_session`
1. **Target:** `aclose` / `_ServerSession.stop`. 2. **Core behavior:** closing twice is safe and ends
   every owner task and client context. 3. **Behavior under test:** two session tasks exist after
   open; none after the double close; each context exited exactly once. 4. **Type:** integration.
5. **Real vs mocked:** real gateway; task-set and event snapshots. 6. **Evidence:** close-event
   count of 1 catches both a leak and a double exit.

### T38 — `test_t38_a_session_can_be_closed_from_a_different_task_than_it_was_opened_in`
1. **Target:** the owner-task design. 2. **Core behavior:** the `Client` holds an anyio task group
   that must exit in its entering task; `open`/`aclose` may be called from different caller tasks.
3. **Behavior under test:** open in one task, search, close in another → no error, no task left.
4. **Type:** integration. 5. **Real vs mocked:** real gateway/client. 6. **Evidence:** without the
   owner task, exiting the group from another task raises; this exercises the documented guarantee.

### T39 — `test_t39_failed_connect_of_one_server_releases_the_other_and_raises`
1. **Target:** `_start_sessions` + `open` cleanup. 2. **Core behavior:** one server failing to
   connect raises `McpConnectionError` and tears the other down. 3. **Behavior under test:** Firecrawl
   connect refused → `McpConnectionError(stage="open")`, no session task left, Parallel's context
   exited. 4. **Type:** integration. 5. **Real vs mocked:** real gateway; Firecrawl target is an
   exception. 6. **Evidence:** the close event for the already-open Parallel session is the leak
   guard a plain "it raises" check would miss.

### T40 — `test_t40_cancelling_open_mid_connect_leaves_no_task`
1. **Target:** `open` cancellation path. 2. **Core behavior:** cancelling the caller during `open`
   still tears both sessions down. 3. **Behavior under test:** Firecrawl connect hangs; cancel
   `open` → `CancelledError` propagates, no session task left, Parallel's context exited.
4. **Type:** integration. 5. **Real vs mocked:** real gateway; a never-completing connect.
6. **Evidence:** a caller timeout during startup is the realistic way a run is aborted; asserting
   the task set and close event proves nothing leaks.

---

## 10. Concurrency and the shared client

### T41 — `test_t41_concurrent_searches_stay_within_the_bound_and_keep_their_own_results`
1. **Target:** per-server search semaphore + shared `Client`. 2. **Core behavior:** in-flight searches
   never exceed `search_concurrency`, and each returns its own result. 3. **Behavior under test:** 10
   concurrent searches with bound 4 → observed max in `(1, 4]`; results' objectives and excerpt text
   match their own requests, in order. 4. **Type:** integration. 5. **Real vs mocked:** tracking
   handler with real overlap. 6. **Evidence:** `max > 1` proves overlap really happened (so `≤ 4` is
   meaningful); the per-call match proves no cross-talk on the shared client.

### T42 — `test_t42_one_failed_call_does_not_abort_a_concurrent_gather`
1. **Target:** the "return, never raise" contract. 2. **Core behavior:** a per-call failure must not
   cancel its siblings in an `asyncio.gather`. 3. **Behavior under test:** four concurrent searches,
   one erroring → `[WebSearchResult, ToolFailure, WebSearchResult, WebSearchResult]`. 4. **Type:**
   integration. 5. **Real vs mocked:** real gateway. 6. **Evidence:** a raise would propagate out of
   `gather`; the typed mix is the observable outcome the M3 phase loop relies on.

### T43 — `test_t43_map_scrape_and_crawl_share_one_firecrawl_pool`
1. **Target:** `_firecrawl_sem`. 2. **Core behavior:** one slot pool bounds every Firecrawl call
   (vendor rate limit), whichever operation. 3. **Behavior under test:** a map, a crawl and five
   scrapes concurrently with pool size 2 → observed max in-flight is exactly 2; each scrape returns
   its own page. 4. **Type:** integration. 5. **Real vs mocked:** a shared in-flight tracker on all
   three tools. 6. **Evidence:** `== 2` shows both overlap and the bound across *all three*
   operations (a crawl on a different pool would push it to 3).

### T44 — `test_t44_a_saturated_firecrawl_pool_does_not_starve_search`
1. **Target:** per-server pools. 2. **Core behavior:** a slow Firecrawl call must not block searches.
3. **Behavior under test:** with the only Firecrawl slot held by a blocked scrape, a search still
   completes within 2 s. 4. **Type:** integration. 5. **Real vs mocked:** blocking scrape handler.
6. **Evidence:** the bounded wait turns a shared-pool bug into a deterministic failure, not a hang.

### T45 — `test_t45_a_call_waiting_out_its_backoff_does_not_hold_the_pool_slot`
1. **Target:** `_call_with_retry` slot scope. 2. **Core behavior:** the slot is held only across the
   live call, not the backoff sleep. 3. **Behavior under test:** with pool size 1, a scrape parked in
   its backoff does not block another scrape, which completes. 4. **Type:** integration.
5. **Real vs mocked:** `_async_sleep` replaced by an event-gated sleep so the backoff is held open.
6. **Evidence:** the second scrape can only finish if the slot was released during the sleep.

### T46 — `test_t46_cancelling_an_in_flight_call_frees_its_slot_and_keeps_the_session` (search / scrape)
1. **Target:** caller-cancellation safety (V2a/V2b "cancelled call mid-flight"). 2. **Core behavior:**
   cancelling one call releases its pool slot and leaves the session usable. 3. **Behavior under
   test:** with pool size 1, cancel a blocked call (`CancelledError` propagates), then a follow-up
   call completes within 2 s. 4. **Type:** integration. 5. **Real vs mocked:** blocking handler.
6. **Evidence:** with one slot, the follow-up completes only if the slot was freed and the session
   survived; this automates the sample runner's manual cancel check.

---

## 11. Secret hygiene and the production client factory

### T47 — `test_t47_keys_never_reach_logs_or_failure_messages`
1. **Target:** logging and `ToolFailure.message` construction. 2. **Core behavior:** API keys live
   only in `McpServerConfig.api_key`. 3. **Behavior under test:** with a sentinel key, failing
   search/map/scrape produce messages and DEBUG logs that never contain it. 4. **Type:**
   integration. 5. **Real vs mocked:** real gateway; `caplog` at DEBUG. 6. **Evidence:** asserts
   the logs are non-empty first (attempt records exist), so absence of the secret is meaningful.

### T48 — `test_t48_composition_root_gateway_serves_typed_results_over_real_http`
1. **Target:** `create_mcp_tool_gateway` + `_streamable_http_factory`. 2. **Core behavior:** the
   composition root builds a gateway that works end to end. 3. **Behavior under test:** settings
   pointing at two loopback MCP servers → `open`, `search_web`, `map_site`, `scrape_page` return
   typed results. 4. **Type:** e2e. 5. **Real vs mocked:** production factory, `httpx2`, real HTTP;
   only the vendor is a local fake. 6. **Evidence:** the only test that runs the factory production
   uses (all others inject their own), guarding SDK API drift in `Client`/`streamable_http_client`.

### T49 — `test_t49_bearer_header_is_sent_only_when_a_key_is_configured`
1. **Target:** `_streamable_http_factory` headers + `_normalize_key`. 2. **Core behavior:** the
   bearer header is attached only when a key exists; blank equals no key. 3. **Behavior under
   test:** whitespace Parallel key → no `Authorization` on any request; Firecrawl key → every
   request carries `Bearer fc-key`. 4. **Type:** e2e. 5. **Real vs mocked:** as T48; an ASGI wrapper
   records headers. 6. **Evidence:** the header is read off the real wire request server-side, so
   a header that is built but not sent (or `Bearer ` with a blank key) fails.

---

## Coverage map (behavior → test)

| Decision / behavior | Tests |
| --- | --- |
| Capability match; crawl not required | T1–T3 |
| Probe: ordering/URL, unexpected shape, transient vs shape | T4–T6 |
| Search parse, structured preference, empty, unreadable | T7–T10 |
| Map: unfiltered/uncapped, legacy strings, empty, degrade+log, unreadable | T11–T15 |
| Scrape: reported URL, arguments, empty page, unreadable | T16–T19 |
| Retry: non-transient once, transient twice+backoffs, recovery, transport, timeout, logging | T20–T26 |
| Classification of unreachable exception types | T27 |
| Argument guards and pre-open guard | T28–T29 |
| Crawl: args, inline, poll, no re-issue, re-read, deadline, de-mask | T30–T36 |
| Lifecycle: idempotent close, cross-task close, failed open, cancelled open | T37–T40 |
| Concurrency: bound, no cross-talk, gather isolation, pools, backoff slot, cancel | T41–T46 |
| Secrets; production factory + bearer header over real HTTP | T47–T49 |

**Deliberately not planned:** live vendor calls (V2a/V2b stay manual), SDK connect mechanics,
`Settings` loading, dataclass immutability, and `McpServerConfig`/result-dataclass field plumbing.

---

## To-do

- [x] Write the tests from each entry above → `test_c3_1_1_mcp_tool_gateway.py`
- [x] Run them → **76 passed** (49 test functions; parametrized cases counted)
- [x] Verify each fails for the right reason (break the behavior; confirm the test catches it) →
      see "Verification record" below

---

## Verification record

**Run:** `python -m pytest src/services/deep_search/feature_tests/test_c3_1_1_mcp_tool_gateway.py -q`
→ **76 passed** (~6–15 s, no network, no keys). The pre-existing
`backend/tests/services/deep_search/test_mcp_tool_gateway.py` (54 tests) also passes unchanged.

**Break-the-behavior sweep.** 30 single-line bugs were injected into `src/clients/mcp_tools.py` one at
a time (file restored byte-for-byte afterwards; SHA-256 `ce0b9be3…` verified), and the suite was run
against each. 29 of 30 were caught, each by the test(s) that own that behavior:

| # | Injected bug | Caught by |
| --- | --- | --- |
| M01 | scrape `formats` arg no longer required | T2[scrape_arg] |
| M02 | `firecrawl_map` no longer required | T2[map_tool] |
| M03 | backoffs swapped to (3.0, 2.0) | T6, T21–T25 |
| M04 | search does not retry rate limits | T21, T22 |
| M05 | search does not retry transport errors | T23, T24 |
| M06 | crawl `allowExternalLinks` = true | T30 |
| M07 | crawl start retried on timeout (double bill) | T33 |
| M08 | timed-out status read not re-asked | T34 |
| M09 | pool slot held across backoff sleep | T45 |
| M10 | API key written into the session log | T47 |
| M11 | text block preferred over structured content | T8 |
| M12 | unknown search shape returned as empty result | T10[no_hit_list_key] |
| M13 | blank `sourceURL` accepted | T5, T19 |
| M14 | `open()` does not clean up on failure/cancel | T2, T5, T39, T40 |
| M15 | map result capped at 50 | T11 |
| M16 | crawl `limit` not validated | T28 |
| M17 | search pool unbounded | T41 |
| M18 | crawl uses the search pool | T43 |
| M19 | one pool shared by search and Firecrawl | T43 |
| M20 | probe skipped | T4, T5, T6 |
| M21 | bearer header always sent | T49 |
| M22 | blank key not normalised to "no key" | T49 |
| M23 | deadline message drops the job id | T35 |
| M24 | caller cancellation swallowed | T46 |
| M25 | transport errors not classified | T23, T24, T27 |
| M26 | scrape asks for html, not markdown | T17 |
| M27 | empty search result turned into a failure | T9 |
| M28 | skipped map links not logged | T14 |
| M29 | inline crawl pages polled anyway | **survived** — see below |
| M30 | attempt log drops the page `target` | T26 |

**M29 survived, and why.** T31's start body had completed pages but no job id, so the mutated code
reached the same result through its fallback branch. T31 was then strengthened: the start body now
carries both `id` and completed pages and asserts `job_id == "job-inline"` and zero status polls,
which the mutated code would fail (it would poll). The strengthened test passes on the real code
(76 passed). **The M29 mutant has not been re-run against the strengthened T31**; that re-check is
pending.

---

## Iteration 3 additions (fixes A4, M5–M10)

Added to `test_c3_1_1_mcp_tool_gateway.py` (T50–T61) for the "Fixes to be incorporated in iteration"
spec. The rate-limited retry backoff changed from `[2.0, 3.0]` to `[30.0, 60.0]` (M8); the existing
rate-limit assertions in both suites were updated, while timeout/transport cases keep `[2.0, 3.0]`.

| Test | Fix | Behavior proven |
| --- | --- | --- |
| T50 | M6 | an `MCPError` SSE-ended disconnect classifies `transport`, is retried on the same session (backoff `[2.0, 3.0]`), and recovers |
| T51 | M6 | a persistent SSE disconnect returns `ToolFailure(transport)`, not `tool_error` |
| T52 | M7, M8 | a `429` wrapped in an `MCPError` classifies `rate_limited` and uses the window-clearing backoff `[30.0, 60.0]` |
| T53 | M6, M7 | unit: `_classify_failure` maps SSE-ended→transport, wrapped-429→rate_limited, other MCPError→tool_error |
| T54 | A4 | `batch_scrape` polls a job to completion; pages keyed by their own `metadata.sourceURL`; totals carried |
| T55 | A4 | the `next` cursor is followed so all pages are collected |
| T56 | A4 | a per-URL failure inside a completed job rides `failed_urls` and logs `mcp.batch_pages_failed` (degrade, not whole-job failure) |
| T57 | A4 | an unrecognised batch status is `ToolFailure(unparseable)`, not polled to the deadline |
| T58 | A4, M10 | a never-completing batch job returns `ToolFailure(timeout)` carrying the job id |
| T59 | A4 | bad input (empty list, non-http URL) raises `ValueError` before any call |
| T60 | A4 | batch is not capability-checked (user decision): `open()` succeeds without the tool, the gap is a per-call `ToolFailure` |
| T61 | M5 | real HTTP: a scrape whose body streams for ~6 s (past httpx's old 5 s read default) still completes, proving the factory sets `read=None` |

**Deferred to a live runner pass (OV-8, OV-10):** the exact rate-limit window and the measured
queue-inclusive timeout values; the starting values (30/60 s backoff, 60/60 s budgets) are in code.

## Iteration 5 updates (M13 fan-out, A7 rate limiter, R2/R3/R4 removals)

The hosted `/v2` endpoint exposes no batch tool and the connect-time probe is removed, so:

**Retired:** T4–T6 (probe); T54–T60 (the A4 batch-job cases); and the iteration-4 resolver unit
tests (A5/M11), since `batch_scrape`/`BatchScrapeResult`/the resolver/the probe no longer exist.
OV-11 (batch tool-name discovery) is retired with them.

**Replaced / added** in `test_c3_1_1_mcp_tool_gateway.py` (the T54–T58 ids are reused):

| Test | Point | Behavior proven |
| --- | --- | --- |
| T54 | M13 | `scrape_pages` fans out one `scrape_page` per URL; each page keyed by its own `metadata.sourceURL`; `total`/`completed` carried |
| T55 | M13 | a per-URL failure rides `failed_urls` and logs `mcp.scrape_pages_partial` (degrade, not a whole-call failure); the rest complete |
| T56 | M13 | bad input (empty list, non-http URL) raises `ValueError` before any call |
| T57 | M13, M9 | the fan-out's in-flight scrapes never exceed `FIRECRAWL_CONCURRENCY` (the shared `_firecrawl_sem`) |
| T58 | A7 | unit: `_TokenBucket(capacity)` admits the first `capacity` acquisitions immediately and paces the next until the window refills |
| T61 | M5 | unchanged real-HTTP slow-stream test (probe-free `open()`) |

The second suite (`tests/services/deep_search/test_mcp_tool_gateway.py`) carries the same
replacements under descriptive names, plus `test_token_bucket_paces_acquisitions_to_capacity_per_window`.

**A7 note:** both gates (≤2 concurrent via `_firecrawl_sem`, ≤10/min via the token bucket) apply to
every Firecrawl call; `web_search` (Parallel) is excluded. The test `_gateway` helper defaults the
bucket effectively unlimited so multi-call tests are not paced; the bucket's pacing is proven by the
dedicated `_TokenBucket` unit test. The fixtures still register provisional `firecrawl_batch_scrape` /
`firecrawl_check_batch_scrape_status` tools, now unused and harmless (the gateway calls neither).


## Iteration 6 — raw tool-definition snapshot

Both gateway suites include `test_iteration6_*` contract cases using recording listing clients
through the existing session-owner seam. No external services or API keys are required.

- Paginated listings preserve all tools, nullable descriptions, empty schemas, nested constraints,
  `$ref` chains and `$defs`; identical names on different servers retain distinct definitions.
- Editing an SDK fixture or a returned nested schema does not alter the retained snapshot.
- Repeated getter/open/explicit verification reads make no additional listing requests.
- Listing, capability and invalid-schema failures settle sibling work and publish nothing.
- Before/during open, after failed/cancelled setup and after close, access raises
  `McpConnectionError(stage="get_tool_definitions")`.
- A close queued during opening serializes correctly; reopening gets a fresh snapshot while old
  caller copies remain independent. Existing required search/map/scrape checks still apply.
- Listing and availability events share a setup ID; only publication and invalidation emit state
  transitions. Repeated local reads and no-op close emit no extra state transitions.
