# Test Plan — R2 Mechanism 3, Sub-component C3.1.1 (MCP Tool Gateway for Parallel and Firecrawl)

**Status: PLAN ONLY — review gate.** No test code is written yet. After approval, the to-do list at
the bottom is executed: tests are written into
`backend/src/services/deep_search/feature_tests/` and each is verified to fail for the right reason.

**Resource under test:** `src/clients/mcp_tools.py` — `McpToolGateway` and its module-level pure
helpers, plus the `create_mcp_tool_gateway` composition root. Implementation plan:
`feature_context/r2_mechanism_3_c3_1_1_implementation_plan.md`.

---

## Guiding decision for real-vs-mock (applies to the whole plan)

> Test the decisions the gateway makes, at a boundary where the outcome is observable, using real
> dependencies for what can actually be wrong (our retry/poll/parse/lifecycle logic, the real
> `mcp.Client` and its in-process transport) and fakes only for what is costly or outside the system
> (the hosted Parallel/Firecrawl servers, wall-clock sleep).

**What is REAL in every integration entry below:** the full `McpToolGateway` logic, the real
`mcp.Client`, the real in-process MCP transport, `_ServerSession` owner tasks, the per-server
semaphores, and the real parsers/classifier reached through the public methods.

**What is FAKED, and why it is legitimate (not hiding a bug):**
- **The hosted MCP servers** → replaced by an in-process `mcp.server.MCPServer` whose tools are
  configurable async handlers, injected through the gateway's own `client_factory` seam. This is the
  "outside the system / costs money / non-deterministic / network" edge. The gateway still talks
  real MCP protocol to it, so our logic is not mocked — only the vendor is.
- **`mcp_tools._async_sleep`** → monkeypatched to record its argument and return immediately, so
  retry/poll backoffs are asserted by value without real waiting (determinism). Real `asyncio.timeout`
  with a tiny per-call budget is still used where a genuine timeout must fire.
- **A crafted exception object** (one unit entry only) → where a branch of `_classify_failure`
  (transport error, HTTP 429) cannot be reached through the in-process fake without real network.

**Not tested (per the skill's "do not test" list):** the `mcp` SDK itself (that `Client` connects,
that `MCPServer` serves), pydantic/dataclass construction, `Settings` env loading, and the live
sample runner (`mcp_tool_gateway_sample_run.py` — it spends credits, hits the network, and is
non-deterministic; its V2a/V2b checks stay manual, exactly as the plan locks them).

**Type labels:** `integration (in-process MCP server; no network)` = full path through the real SDK
client with the vendor faked; `unit` = a pure function exercised in isolation.

---

## Capability check (`open` / `verify_capabilities`)

### T1 — `test_open_succeeds_when_both_catalogs_expose_required_tools_and_args`
1. **Target:** `McpToolGateway.open` (→ `verify_capabilities`).
2. **Core behavior:** `open` starts both sessions, then confirms each server lists the required tools
   with the required argument names; it returns normally only when every requirement is met.
3. **Behavior under test:** a complete catalog on both servers lets `open` complete without raising.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway + real `mcp.Client`; two in-process `MCPServer`s exposing
   `web_search(objective, search_queries)`, `firecrawl_crawl(url, limit, maxDiscoveryDepth,
   allowExternalLinks)`, and `firecrawl_check_crawl_status(id)`.
6. **Evidence:** the servers are built from the *exact* required names/args, and `open` returning is
   the only observable success signal of the check; if `verify_capabilities` silently skipped the
   match, T2–T4 (which must raise) would fail, so a green T1 plus red-on-break T2–T4 together prove
   the match actually runs rather than being a no-op.

### T2 — `test_missing_required_tool_raises_tool_unavailable_at_verify`
1. **Target:** `verify_capabilities` (tool-absent branch of `_require`).
2. **Core behavior:** a required tool absent from a server catalog fails fast at connect, not mid-run.
3. **Behavior under test:** Firecrawl without `firecrawl_crawl` raises `McpToolUnavailableError` with
   `stage == "verify_capabilities"`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Firecrawl in-process server built *without* the crawl tool;
   Parallel complete. (This is the same code path that a keyless Firecrawl hits in production, where
   the hosted server lists no crawl tool — noted so we do not add a redundant "keyless" twin.)
6. **Evidence:** the only difference from T1 is the removed tool, and the assertion is the specific
   typed error + stage; a parser/altitude regression that stopped checking tool presence would let
   this call succeed, so the raise is caused by the missing tool, not restated by the test.

### T3 — `test_missing_required_argument_raises_tool_unavailable`
1. **Target:** `verify_capabilities` (argument-absent branch of `_require`).
2. **Core behavior:** a required argument missing from an otherwise-present tool still fails the check.
3. **Behavior under test:** a Parallel `web_search` declared with `objective` but no `search_queries`
   raises `McpToolUnavailableError`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel server whose `web_search` signature omits
   `search_queries` (so its published `input_schema.properties` lacks it); Firecrawl complete.
6. **Evidence:** the tool exists, so only the *argument* branch can produce the raise; this
   distinguishes "tool present" from "tool usable with our arguments", which the tool-only test (T2)
   cannot prove.

### T4 — `test_missing_status_tool_raises_tool_unavailable`
1. **Target:** `verify_capabilities` (status tool is independently required).
2. **Core behavior:** because every crawl result is read via `firecrawl_check_crawl_status`, its
   absence must fail the check even when `firecrawl_crawl` is present.
3. **Behavior under test:** Firecrawl with `firecrawl_crawl` but no `firecrawl_check_crawl_status`
   raises `McpToolUnavailableError`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Firecrawl server with the crawl tool but no status tool.
6. **Evidence:** protects a specific, easily-dropped requirement line; if someone removed the status
   check, T1/T2/T3 would still pass but this would go green on a broken config — so it guards a real
   regression the others miss.

---

## Typed search results (`search_web` + parsers)

### T5 — `test_search_returns_typed_result_with_stamped_timestamp_and_echoed_request`
1. **Target:** `search_web` + `_parse_search_result`.
2. **Core behavior:** a successful `web_search` is parsed into `WebSearchResult` carrying the
   objective/queries it was asked with, a non-empty `retrieved_at`, and one `SearchExcerpt` per hit.
3. **Behavior under test:** the happy path produces the typed contract with fields populated from the
   server body.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel server returning a known hit (`url`, `title`, `text`).
6. **Evidence:** asserts the excerpt's `url`/`text` equal the *server-provided* values (not constants
   the test also set on the request) and that `objective`/`search_queries` echo the request — proving
   the parser reads the body and the method stamps/echoes, not that it returns a canned object.

### T6 — `test_empty_search_hit_list_returns_zero_excerpts_not_a_failure`
1. **Target:** `search_web` + `_parse_search_result` (empty-body rule).
2. **Core behavior:** an empty result set is a valid `WebSearchResult(excerpts=())`, never a failure.
3. **Behavior under test:** a server body with `{"results": []}` yields a `WebSearchResult` with
   `excerpts == ()` and a stamped `retrieved_at`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel server returning an empty results list.
6. **Evidence:** the boundary (zero hits) is the classic spot where "no data" is wrongly turned into
   an error; asserting a `WebSearchResult` (not a `ToolFailure`) with `()` proves the documented rule.

### T7 — `test_tool_error_result_returns_toolfailure_not_raised`
1. **Target:** `search_web` + `_single_call` + `_classify_failure`.
2. **Core behavior:** an `is_error` tool result degrades to a returned `ToolFailure`, so one bad call
   never aborts a concurrent gather.
3. **Behavior under test:** a Parallel tool that errors with a non-rate-limit message makes
   `search_web` **return** `ToolFailure(kind="tool_error")` rather than raise.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel tool raising `ToolError("...broken...")` (surfaces as
   `is_error`).
6. **Evidence:** the test would fail if the method raised (pytest surfaces the exception) — so the
   "returned, not raised" contract and the `tool_error` classification are both actually exercised.

### T8 — `test_unrecognized_search_body_returns_toolfailure_unparseable`
1. **Target:** `search_web` + `_decode_body` / `_parse_search_result`.
2. **Core behavior:** a body that is neither structured nor decodable JSON (nor a known shape)
   becomes `ToolFailure(kind="unparseable")`, not a crash.
3. **Behavior under test:** a tool returning a non-JSON text blob yields `ToolFailure(unparseable)`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel tool returning a plain non-JSON string.
6. **Evidence:** proves the parser's failure branch is reachable through the public method and does
   not propagate a `JSONDecodeError` to the caller — a real robustness guarantee for C3.1.2.

### T9 — `test_search_parses_structured_content_shape`
1. **Target:** `_decode_body` structured-content branch, via `search_web`.
2. **Core behavior:** parsers prefer `structured_content` when the server provides it, before falling
   back to decoding text blocks.
3. **Behavior under test:** a server result carrying `structured_content` (not just text) is parsed
   into the same typed excerpts.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel tool declared with an output schema so the SDK sets
   `structured_content` on the result (the other search tests exercise the text-JSON branch).
6. **Evidence:** this is a distinct decode equivalence class; without it, a regression that only read
   text blocks would pass every other search test yet silently drop structured payloads in prod.

---

## Search retry policy (`_call_with_retry`)

### T10 — `test_transient_search_failure_retries_twice_with_backoffs_then_fails`
1. **Target:** `search_web` → `_call_with_retry`.
2. **Core behavior:** transient kinds (timeout/transport/rate-limited) retry twice with 2.0 s then
   3.0 s backoff; exhaustion returns a `ToolFailure`.
3. **Behavior under test:** a persistently rate-limited tool is attempted exactly 3 times, the gateway
   sleeps `[2.0, 3.0]`, and the final outcome is `ToolFailure(kind="rate_limited")`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel tool that always raises `ToolError("rate limit
   exceeded")` and counts its invocations; `mcp_tools._async_sleep` monkeypatched to record durations
   instead of waiting.
6. **Evidence:** asserts the *observed* attempt count (3) and the *recorded* sleep sequence
   (`[2.0, 3.0]`) — numbers that come from the control flow, not from re-reading a constant; a
   wrong backoff or an off-by-one in the retry loop changes these and fails the test.

### T11 — `test_non_transient_search_failure_makes_single_attempt`
1. **Target:** `search_web` → `_call_with_retry` (non-retry branch).
2. **Core behavior:** a non-transient `tool_error` is not retried.
3. **Behavior under test:** a tool erroring with a generic (non-rate-limit) message is invoked exactly
   once and returns `ToolFailure(kind="tool_error")` with no recorded sleeps.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel tool raising a generic `ToolError` and counting calls;
   `_async_sleep` recorded.
6. **Evidence:** attempt count == 1 and empty sleep log prove the retry gate actually discriminates by
   kind, rather than retrying everything or nothing.

---

## Crawl arguments & validation (`crawl_site`)

### T12 — `test_crawl_sends_depth_and_disables_external_links`
1. **Target:** `crawl_site` argument construction.
2. **Core behavior:** `crawl_site` sends `maxDiscoveryDepth` from its `depth` arg and always sets
   `allowExternalLinks=false`.
3. **Behavior under test:** the arguments the Firecrawl tool actually receives include
   `maxDiscoveryDepth == depth` and `allowExternalLinks is False`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Firecrawl crawl tool that captures the arguments it is called
   with and returns a completed page set.
6. **Evidence:** the interaction (what is sent to the vendor tool) *is* the behavior here — a wrong
   key name or a missing `allowExternalLinks=false` would change crawl scope/cost in production, so an
   argument-capture assertion is warranted (not brittle).

### T13 — `test_invalid_crawl_arguments_raise_value_error`
1. **Target:** `crawl_site` input validation.
2. **Core behavior:** `limit >= 1`, `depth >= 0`, and an `http(s)` URL are required; otherwise
   `ValueError` before any call.
3. **Behavior under test:** `limit=0`, `depth=-1`, and `url="ftp://x"` each raise `ValueError`
   (representative members of the validation equivalence class).
4. **Type:** integration (in-process MCP server; no network) — gateway opened, but the guard fires
   before the tool is reached.
5. **Real vs mocked:** real gateway; a Firecrawl tool that records whether it was called.
6. **Evidence:** asserts both the raise *and* that the crawl tool was never invoked — proving the
   guard rejects bad input up-front rather than after spending a call.

---

## Crawl result shapes & job reading (`crawl_site` / `_read_crawl_job`)

### T14 — `test_crawl_returns_pages_when_start_response_has_them`
1. **Target:** `crawl_site` + `_parse_crawl_result` (inline-pages shape).
2. **Core behavior:** if the start response already carries completed pages, they are accepted and
   returned as a `CrawlResult` without polling.
3. **Behavior under test:** a start response with `status="completed"` and a page list yields a
   `CrawlResult` whose `pages` reflect the body, and the status tool is never polled.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Firecrawl crawl tool returning completed pages; status tool that
   counts calls.
6. **Evidence:** asserts page content from the body *and* status-poll count == 0 — proving the
   "accept inline pages" branch is taken, distinct from the polling branch in T15.

### T15 — `test_crawl_polls_job_id_to_completion`
1. **Target:** `crawl_site` + `_read_crawl_job` + `_parse_crawl_status` (job-id shape).
2. **Core behavior:** when the start response is a job id, the gateway polls
   `firecrawl_check_crawl_status` on the same client until the job completes, then returns the pages.
3. **Behavior under test:** start returns `{"id": "job-9"}`; the status tool returns "running" once
   then "completed+pages"; the result is a `CrawlResult` with `job_id == "job-9"` and the pages.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Firecrawl start tool returning a job id; status tool stepping
   running→completed and counting calls; `_async_sleep` recorded (poll interval not really waited).
6. **Evidence:** asserts the job id is carried onto the result and that the status tool was polled
   more than once ending in completion — proving the poll loop advances state rather than returning
   the first response.

### T16 — `test_timed_out_status_read_retries_same_job_without_reissuing_crawl`
1. **Target:** `_read_crawl_job` timeout-recovery path.
2. **Core behavior:** a timed-out status read is re-sent **with the same job id on the same client**;
   `firecrawl_crawl` is **never** issued a second time (would create a second billed job).
3. **Behavior under test:** the first status read exceeds the per-call timeout; the gateway re-reads
   the same id and completes; `firecrawl_crawl` is called exactly once, the status tool twice (always
   with the same id), and the result is a `CrawlResult`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway with a small `firecrawl` `call_timeout_seconds`; start tool
   counting calls; status tool that sleeps past the timeout on call 1 then completes on call 2, and
   asserts the id it receives each time; real `asyncio.timeout` fires the timeout.
6. **Evidence:** the must-not-double-bill guarantee *is* an interaction, so asserting
   `crawl_calls == 1` and `status_calls == 2` (same id) is the right, non-tautological check; a
   regression that re-issued the crawl or built a new client on timeout would change these counts.

### T17 — `test_crawl_deadline_reached_returns_timeout_carrying_job_id`
1. **Target:** `_read_crawl_job` deadline branch.
2. **Core behavior:** if polling never completes within the overall crawl deadline, the gateway
   returns `ToolFailure(kind="timeout")` whose message carries the job id (so the job is not lost).
3. **Behavior under test:** a status tool stuck on "running" past a shortened deadline yields
   `ToolFailure(timeout)` and the job id appears in `message`.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; `mcp_tools.CRAWL_DEADLINE_SECONDS` monkeypatched to a tiny value;
   status tool always "running"; `_async_sleep` recorded so the loop spins without real waiting.
6. **Evidence:** asserts the typed failure *and* the job id substring in the message — proving the
   deadline is enforced and the recovery handle is preserved, not silently dropped.

---

## Session scope & lifecycle (`_ServerSession`, `open`, `aclose`)

### T18 — `test_call_before_open_raises_connection_error`
1. **Target:** `search_web` / `McpToolGateway` session guard (`_ServerSession.client`).
2. **Core behavior:** a tool call before `open()` has no session and must raise, not act on a `None`.
3. **Behavior under test:** `search_web` on a never-opened gateway raises `McpConnectionError`.
4. **Type:** integration (in-process MCP server; no network) — no session is ever started.
5. **Real vs mocked:** real gateway; factory present but never invoked.
6. **Evidence:** proves the pre-open guard exists and surfaces a typed error (a caller can handle it),
   rather than an `AttributeError` from a missing client.

### T19 — `test_aclose_is_idempotent`
1. **Target:** `aclose` / `_ServerSession.stop`.
2. **Core behavior:** `aclose` can be called repeatedly (the caller closes, and `AmenitySearch.aclose`
   may close again) with no error.
3. **Behavior under test:** `open()` then `aclose()` twice completes without raising.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway + in-process servers.
6. **Evidence:** the double-close is the exact production scenario (gateway closed by the mechanism
   and again by `AmenitySearch.aclose`); a non-idempotent stop would raise on the second call.

### T20 — `test_failed_open_raises_connection_error_and_leaves_no_running_task`
1. **Target:** `open` / `_start_sessions` cleanup.
2. **Core behavior:** if one session cannot start, `open` stops the other and raises, leaving no owner
   task running (no leak).
3. **Behavior under test:** a factory that raises for Firecrawl makes `open` raise
   `McpConnectionError`, and no `mcp-session-*` task remains afterwards.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway; Parallel in-process server (starts fine); Firecrawl factory entry
   is an exception (connect failure).
6. **Evidence:** snapshots `asyncio.all_tasks()` named `mcp-session*` before/after and asserts equality
   plus the raise — proving cleanup actually tears down the already-started owner task, a real
   resource-leak guard that a plain "it raises" assertion would miss.

---

## Concurrency & the shared client

### T21 — `test_concurrent_searches_respect_semaphore_and_return_own_results`
1. **Target:** `search_web` under `asyncio.gather`; per-server semaphore + shared `Client`.
2. **Core behavior:** many concurrent searches on one shared client never exceed the semaphore's
   in-flight bound and each returns its own (non-crossed) result.
3. **Behavior under test:** 10 concurrent `search_web` calls with `search_concurrency=4` observe
   max in-flight ≤ 4, and each returned `WebSearchResult` matches the objective it was asked with.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway with `search_concurrency=4`; Parallel tool that tracks live
   concurrency (increment/await/decrement) and echoes the objective into its result; real sleeps
   inside the handler (not the gateway backoff) so overlap actually occurs.
6. **Evidence:** the observed max-concurrency ≤ 4 proves the semaphore bounds in-flight work, and the
   per-call objective match proves responses are not swapped on the shared client — both are failures
   that only appear under real concurrency, not in single-call tests.

### T22 — `test_timed_out_call_leaves_same_client_usable_without_rebuild`
1. **Target:** the locked "no session/`Client` replacement" decision, via `search_web`.
2. **Core behavior:** a fully-timed-out call returns `ToolFailure(timeout)`, and the **same** session
   serves the next call — the gateway never rebuilds the client on timeout.
3. **Behavior under test:** objective "first" times out on every attempt → `ToolFailure(timeout)`;
   a following "second" search succeeds on the same session; the client factory was invoked exactly
   once for Parallel (open only).
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway with tiny `parallel` `call_timeout_seconds`; Parallel tool that
   sleeps past the timeout for "first" and returns immediately for "second"; a factory call counter;
   `_async_sleep` recorded.
6. **Evidence:** the factory-invocation count (== 1 for Parallel) is the decisive proof that no new
   client was built after the timeout — the interaction *is* the "no replacement" behavior; pairing it
   with a successful follow-up proves the session survived rather than being quietly re-created.

---

## Secret hygiene

### T23 — `test_api_keys_never_appear_in_logs_or_failure_messages`
1. **Target:** logging in `_ServerSession.start` / `_log_attempt` and `ToolFailure.message` building.
2. **Core behavior:** server API keys live only in `McpServerConfig.api_key`; they never enter log
   records, exception text, or `ToolFailure.message`.
3. **Behavior under test:** with a distinctive api key configured, a failing search produces a
   `ToolFailure` whose message omits the key, and the captured `homescout.deep_search` log omits it.
4. **Type:** integration (in-process MCP server; no network).
5. **Real vs mocked:** real gateway built with a sentinel `api_key`; Parallel tool that fails;
   `caplog` capturing the `homescout.deep_search` logger.
6. **Evidence:** asserts the sentinel string is absent from both `result.message` and `caplog.text` —
   a direct, observable security property; if any log line or message interpolated the config, the
   sentinel would appear and fail the test.

---

## Failure classification (narrow unit — unreachable branches)

### T24 — `test_classify_failure_maps_transport_and_rate_limited_exceptions`
1. **Target:** `mcp_tools._classify_failure` (pure function).
2. **Core behavior:** maps an exception/`is_error` result to a `ToolFailureKind` — a transport error
   → `transport` (retryable for search), an HTTP-429-bearing error → `rate_limited`.
3. **Behavior under test:** `_classify_failure(httpx2-style connection error)` → `"transport"`, and
   `_classify_failure(error with status_code 429)` → `"rate_limited"`.
4. **Type:** unit.
5. **Real vs mocked:** the real function; inputs are synthetic exception instances. **Justification
   for direct testing (an exception to "don't test private helpers"):** the transport and 429
   classes cannot be produced by the in-process fake without real network, yet a misclassification
   has real stakes — a transport error wrongly classed non-retryable would drop recoverable calls,
   and a missed 429 would hammer a rate-limited server.
6. **Evidence:** feeds inputs whose *only* salient property is the transport type / 429 status and
   asserts the kind — proving the classification rule, not the rest of the call path. (The
   `tool_error`, `rate_limited`-via-text, and `timeout` classes are already covered observably by
   T7, T10, and T22 through the public methods, so they are not re-tested here.)

---

## Coverage map (behavior → test)

| Decision / behavior | Tests |
| --- | --- |
| Capability match (pass / tool / arg / status) | T1, T2, T3, T4 |
| Typed search result + stamping + echo | T5 |
| Empty result is valid | T6 |
| `is_error` → returned `ToolFailure` | T7 |
| Unparseable body → `unparseable` | T8 |
| structured_content decode branch | T9 |
| Retry: transient twice + backoffs; non-transient once | T10, T11 |
| Crawl args (depth, no external links) | T12 |
| Crawl input validation | T13 |
| Crawl inline-pages vs job-id-poll shapes | T14, T15 |
| Crawl timeout recovery (no re-issue, same id) | T16 |
| Crawl deadline → timeout w/ job id | T17 |
| Pre-open guard | T18 |
| `aclose` idempotent | T19 |
| Failed open: raise + no task leak | T20 |
| Concurrency bound + no cross-talk | T21 |
| No client replacement on timeout | T22 |
| Secret hygiene | T23 |
| Classifier transport / 429 branches | T24 |

**Deliberately not planned:** live Parallel/Firecrawl calls (V2a/V2b stay manual in the sample
runner — costly, networked, non-deterministic); SDK connect/serve mechanics; `Settings` loading;
dataclass immutability. These fail the "can plausibly break in *our* logic / worth a deterministic
automated test" filters.

---

## To-do (executed only after approval)

- [ ] Write the tests T1–T24 into `backend/src/services/deep_search/feature_tests/` (proposed file:
      `test_c3_1_1_mcp_tool_gateway.py`), with the shared in-process `MCPServer` + `client_factory`
      harness, the `_async_sleep` recorder fixture, and the `caplog` hook described above.
- [ ] Run them and verify each fails for the right reason — break the behavior (e.g. drop the status
      `_require` line, flip `allowExternalLinks`, re-issue the crawl on timeout, rebuild the client on
      timeout, interpolate the key into a log) and confirm the matching test catches it.
- [ ] Decide the relationship with the existing
      `backend/tests/services/deep_search/test_mcp_tool_gateway.py`: move it under `feature_tests`
      and reconcile, or designate one suite canonical — avoid maintaining two copies.
