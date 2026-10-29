# R3 — Specific Metric Resolution: Sub-Component Specs (R3.M1 & R3.M2)

> Promoted from "R2 Mechanism 3" to its own responsibility (R3). Throughout this spec, "M3" /
> "Mechanism 3" refers to this responsibility; its two mechanisms are **R3.M1 — Evidence
> Acquisition** (former C3.1) and **R3.M2 — Resolution** (former C3.2). `C3.1.1` (MCP gateway)
> and `C3.1.2` (shared-caller tool turn) keep their IDs: they are already-built **client
> prerequisites**, not R3 stage methods.

> **Status: DRAFT FOR DISCUSSION.** This surfaces the initial draft so we can finalize specs sub-component by sub-component. Nothing here is implemented. This is not yet an approved implementation plan.

## Context

Feature **Deep Search**, Responsibility 2 (R2), **Mechanism 3** resolves metrics for discovered amenities. This document decomposes the two components defined in `r2_mechanism_3_final_a4b603ba.plan.md`:

- **R3.M1 — Evidence acquisition.** Native function-calling loop: the shared `StructuredLLMCaller` sends tool schemas to the LLM, and the application executes each returned tool call through an MCP client (Parallel `web_search`, Firecrawl `firecrawl_crawl`).
- **R3.M2 — Resolution.** A final structured turn, with no tools, whose evidence is the amenity's `metrics_source_content` (the per-metric evidence store built in R3.M1) rather than the tool-call thread. It commits per-metric values.

The goal of this round is to **finalize the specs** of each sub-component before any implementation.

---

## Locked decisions (carried in, not reopened)

| ID | Decision |
|----|----------|
| D1 (revised) | The LLM decides when to call tools. Order: `web_search` for all metrics → triage → `firecrawl_map` then `firecrawl_scrape` (one scrape per phase-2-eligible metric — unresolved **and** `factual`) for those metrics. |
| D2 | Hosted Streamable HTTP MCP servers with bearer keys. |
| D4 (revised) | **No** shared crawl per site. Each work item independently resolves its website (R3.M1.3 discovery) and runs its own Phase-2 `map`/`scrape`; no crawl cache, no single-flight. (Supersedes the original "one shared crawl per site" — R3.M1.3 / R3.M1.5.) |
| D5 | A failed item gets `null` and the run continues. |
| D6 | One shared `StructuredLLMCaller`, owned by the composition root. |
| D7 | Scrape overrides web on contradiction. |
| RC7 | M3 runs on all M1 records. |
| RC8 | URL first, then the loop. |
| RC9 (revised) | Output is a separate `SpecificMetricsRecord` per amenity. R3.M2.5 combines these with the `PredefinedMetricsRecord`s into one versioned `AmenityMetricsSet` (1.0). `AmenityRecord` → `PredefinedMetricsRecord`; `AmenityRecordSet` removed. |
| RC10 (revised) | `resolution_source` carries exactly two keys: `web_target` always, plus a class-conditional second key set by `evidence_class` — `scrape_target` (factual) or `review_target` (experiential). `verification` holds the bar only; source trust derives from `evidence_class`. |
| — (revised) | M3's Firecrawl tools are `firecrawl_map` + `firecrawl_scrape` (Phase 2 = `map` → select → per-metric `scrape`). `firecrawl_crawl` is **retained in the gateway for future use but unused by M3** (C3.1.1). |

## Prerequisites — upstream changes this plan requires

**Principle:** any change this plan forces in an **already-implemented upstream mechanism** is listed here and must land **before (or together with)** M3 implementation, so M3 stays aligned with the dependencies it builds on. (Downstream *consumers* — C4.1 / C4.2 — are tracked in R3.M2.5, not here, because they adapt to M3's output rather than gate it.)

**Mechanism 6 — metric definition**
- **RC10 (revised) — class-conditional `resolution_source` + new `evidence_class` field (schema change — DONE).** Each LLM-defined metric now carries an explicit **`evidence_class`** (`factual | experiential`) and a `resolution_source` of **exactly two keys**: `web_target` always, plus `scrape_target` (factual) or `review_target` (experiential). At the strict wire level all three keys are present and the off-class secondary is `null`; code enforces exactly-one-per-class (`_metric_rule_failure` → `resolution_source_class_mismatch`). Phase-2 (`firecrawl` scrape) eligibility is read off the class — only factual metrics carry a `scrape_target`. (`ResolutionSourceEntry` / `MetricEntry` / `MetricResolutionSource` / `MetricSpec` in `schemas.py`; validator + transform in `requirement_interpretation.py`.)
- **`evidence_class` replaces the verification source-clause (prompt + field change — DONE).** `verification` is now the **bar only** — the evidentiary standard the evidence must meet — and no longer carries a source-acceptability clause. The factual/experiential signal is the explicit `evidence_class` field, read directly, never parsed from text (`metric_definition_instruction.py`, kept in sync with the condensed copy in `depth_assignment_instruction.py`). **M3-side (R3.M2.1):** review eligibility is read from `evidence_class` — experiential (equivalently, `review_target` present) ⇒ reviews eligible; factual ⇒ reviews rejected. A metric with **no `review_target`** is reviews-blocked by default (structural safety net).

**Mechanism 1.3 — record assembly / state** (from R3.M2.5, RC9 revised)
- Rename `AmenityRecord` → `PredefinedMetricsRecord`; remove `AmenityRecordSet`.
- M1.3 writes `state.predefined_records` as a plain nested dict (no envelope, no version); spec updated in `deep_search_context.md`.
- Retype `state.amenity_records` and add the two state fields M3 populates (`state.specific_records`, `state.amenity_records`). Full detail in R3.M2.5 "Other changes outside M3."

**New dependency — `tldextract` (R3.M1.3 official-URL gate)**
- Add **`tldextract==<pin>`** to the dependency manifest (the gate needs public-suffix-aware SLD extraction; stdlib `urlsplit` alone cannot split `co.uk`-style suffixes). Pin an exact version.
- Vendor an **offline PSL snapshot** and instantiate one module-level `TLDExtract(cache_dir=<snapshot>, suffix_list_urls=[])` so the gate never fetches at runtime (deterministic, reproducible tests, no network dependency).
- Add a **periodic PSL-refresh** maintenance step for the vendored snapshot. Full behavior in R3.M1.3 "Google-provided URL handling."

**C3.1.2 — failure `cause` on `MetricResolutionProviderError` (code change — NOT DONE)** (from the R3.M1.4 / R3.M1.5 provider-failure handling)
- Add a required **`cause`** (`availability` | `content` | `circuit_open`) to `MetricResolutionProviderError`, next to `stage`, and raise it from **both** `call_turn` and `call_structured` when the chain is exhausted. The run-level circuit breaker (R3.M1.5) counts only `availability`, so it cannot be built without this field. Full rule in C3.1.2 "Typed error."; how `cause` is derived (a `failure_class` set on each `LLMProviderError`, then aggregated across the chain) is in R3.M1.4 step 1 "Prerequisite — provider failure class on `LLMProviderError`."

---

## Research that shapes the sub-components

- **Parallel Search MCP.** `web_search` takes `objective` (string), `search_queries` (3–6 word queries, ≥1, 2–3 recommended, operators allowed), optional `session_id` (≤100 chars, reused within a conversation). Bearer key in `Authorization` header.
- **Firecrawl MCP.** `firecrawl_crawl` takes `url`, `limit`, `maxDiscoveryDepth`, `allowExternalLinks`.
  - Current README: the tool polls internally and returns final data. Older versions returned a job id, polled via `firecrawl_check_crawl_status`.
  - Crawl responses can be very large and overflow context → limit depth and page count.
  - Hosted endpoint and keys: Firecrawl's 3.29.1 changelog (2026-10-09) says hosted keyless access was removed and a request without a credential gets 401. Earlier, the keyless endpoint exposed only 3 tools and the crawl tool needed a key. Not verified live.
- **MCP Python SDK.** Session pattern `streamable_http_client(url, http_client=...)` with `ClientSession`, `list_tools()`, `call_tool(name, args)`. A failing tool returns `is_error` (does not raise). Auth headers via a caller-owned `httpx` client.
- **Tool-calling loop.** OpenAI chat completions and Groq share the message cycle. Assistant message carries `tool_calls`; the app returns one `role: tool` message per `tool_call_id`; loop ends when no `tool_calls` return. `parallel_tool_calls` defaults true. Groq does not support `strict` on function tools.
- **Current code.** `StructuredLLMProvider.generate_structured` builds a fixed system+user message pair (no history, no tool path). `AmenitySearch.__init__` takes only Places and Routes clients. The provider-chain fallback is private to R1.

---

## Dependency order

```mermaid
flowchart TD
    subgraph c31 [R3.M1 Evidence acquisition]
        s311[C3.1.1 MCP gateway]
        s312[C3.1.2 Tool turn in shared caller]
        s313[R3.M1.1 Phase tool catalog and call guard]
        s314[R3.M1.2 Result shaping and crawl cache]
        s315[R3.M1.3 Website URL resolution]
        s316[R3.M1.4 Phase loop and triage]
        s317[R3.M1.5 Work items and amenity pipelines]
        s311 --> s313
        s311 --> s314
        s311 --> s315
        s312 --> s316
        s313 --> s316
        s314 --> s316
        s315 --> s316
        s316 --> s317
    end
    subgraph c32 [R3.M2 Resolution]
        s321[R3.M2.1 Schema and instruction]
        s322[R3.M2.2 Resolution turn and body validation]
        s323[R3.M2.3 Conform and verification gate]
        s324[R3.M2.4 Provenance guard]
        s325[R3.M2.5 Result assembly and record write]
        s321 --> s322
        s322 --> s323
        s323 --> s324
        s324 --> s325
    end
    s312 --> s322
    s314 --> s324
    s317 --> s325
```

---

# Mechanism R3.M1 — Evidence Acquisition

> C3.1.1 and C3.1.2 below are already-built client prerequisites (MCP gateway, shared-caller tool
> turn); the R3.M1 stage methods are R3.M1.1–R3.M1.5.

## C3.1.1 — Build the MCP Tool Gateway for Parallel and Firecrawl *(client prerequisite — already built; not an R3 stage)*

**Goal.** Typed async operations over the two hosted MCP servers: `search_web(objective, search_queries)` → Parallel `web_search`; and for Firecrawl, `map_site(url)` → `firecrawl_map`, `scrape_page(url)` → `firecrawl_scrape`, and `scrape_pages(urls)` → **a concurrent fan-out of `firecrawl_scrape` over the app-shortlisted URLs** (the hosted server exposes no batch tool) — the M3 uses — with `crawl_site(url, limit, depth)` → `firecrawl_crawl` **retained for future use but unused by M3**. Each returns typed results or a typed failure. Sessions open/close in one async scope. The connect step verifies the expected tools and argument names exist.

**Problem.** R2 has no MCP client (no `mcp` dependency, no server keys). MCP returns generic content blocks, not typed data. A session is stateful and must open/close in the same async task. A server can rename/remove a tool; without a connect-time check, the failure surfaces mid-run.

**Finalized approach.** High-level `Client` wrapper — one `Client(transport)` per server, transport built with `streamable_http_client(url, http_client=...)`. The wrapper owns the session, handshake, and context management, and offers convenience methods. The `httpx2` client carrying the `Authorization` header is created and owned by the gateway (mcp 2.2.0 depends on `httpx2`, not `httpx`). It is built with an explicit `httpx2.Timeout(connect=10, read=None, write=10, pool=10)`: `read=None` leaves the long-lived SSE response stream unbounded at the transport, so the per-call `asyncio.timeout` and SDK `read_timeout_seconds` are the single duration bound — httpx's 5 s read default must not sever a map/scrape/batch that streams for longer.

**Decisions — generally mandatory**
- **Session scope.** Sessions open at the start of `run_specific_metric_resolution` and close at its end, same task. Not opened in a constructor. `aclose()` closes a leaked session (as existing Google clients do).
- **Authentication.** Bearer keys from `Settings` (`PARALLEL_API_KEY`, `FIRECRAWL_API_KEY`). Keys never logged.
- **Retry & timeouts.** Retry transient failures only (timeout, transport error, rate limit), backing off by kind: timeout/transport get **one** retry after a 2 s wait (`RETRY_BACKOFFS_SECONDS = (2.0,)`); a rate limit waits a window-clearing 30 s then 30 s (`RATE_LIMIT_BACKOFFS_SECONDS = (30.0, 30.0)`, or a response `Retry-After`), because two short (2–3 s) waits fall inside the same throttled minute whereas the two 30 s waits cumulatively span ~60 s from the first `429` and so clear a one-minute window. **The retry limit is per failure kind** — the length of the failed kind's own backoff tuple, not one shared value (see the R3.M1.4 prerequisite "Per-kind gateway retry limits"). Per-call timeouts are queue-inclusive (Firecrawl's clock runs submission→execution): map and scrape 60 s, search 30 s (`scrape_pages` has no job clock — each fanned-out page uses the 60 s scrape timeout). Firecrawl calls are also **paced proactively to ≤10/min by a token bucket** (see Rate limits & concurrency); an over-budget call waits for the window rather than firing and taking a `429`.
- **Error typing.** `is_error` result → typed tool failure. A dropped SSE stream (`MCPError`, "SSE stream ended / reconnection attempts exhausted") is classified `transport`, so it retries on the same session; a `429` is classified `rate_limited` even when the SDK wraps it in an `MCPError` (checked before the transport branch). Connection/protocol failure at connect → MCP error family with `stage`.
- **Test seam.** Gateway is a `Protocol` injected into `SpecificMetricResolution`; a fake stands in for tests.

**Decisions — problem-specific**
- **Capability check.** `tools/list` must contain `web_search` (args `objective`, `search_queries`) on Parallel and **`firecrawl_map` (arg `url`) + `firecrawl_scrape` (args `url`, `formats`)** on Firecrawl. A miss raises `McpToolUnavailableError` before any amenity work. **No batch tool is checked or required — `scrape_pages` calls no MCP batch tool; it fans out `firecrawl_scrape`, which is already required.** **`firecrawl_crawl` is retained/driven but NOT checked** — a server missing it still opens, and the gap surfaces as a per-call `ToolFailure` on the first `crawl_site`. A server missing map/scrape still fails at connect. A missing Firecrawl key is not caught by this check: per Firecrawl's changelog the hosted endpoint answers 401 without a credential, so the session cannot open and `open()` raises `McpConnectionError` first (not verified live).
- **Firecrawl map/scrape operations (M3 path).** `map_site(url)` calls `firecrawl_map` (app-injected homepage `url`) and returns the site's link set as a typed candidate list; `scrape_page(url)` calls `firecrawl_scrape` (`formats: ["markdown"]`, `onlyMainContent`) and returns one typed page. `scrape_pages(urls)` scrapes the app-shortlisted URLs by running one `scrape_page` per URL concurrently (`gather`), each bounded by the shared Firecrawl semaphore (`FIRECRAWL_CONCURRENCY = 2`) and the ≤10/min token bucket, so one failed URL does not fail the rest — the hosted server offers no batch tool, so there is no single job. `scrape_page` is kept for single-page use and is the building block of the fan-out. The LLM never supplies a URL (R3.M1.1).
  - *multi-page output shape.* `scrape_pages` returns a `ScrapeResults` whose `pages` are the successful `ScrapeResult`s (one per URL, keyed by its own `metadata.sourceURL`), with `total`/`completed` counts and the URLs that failed in `failed_urls` (a signalled degrade, logged, not a whole-call failure). Only the field shape is carried over from the former `BatchScrapeResult`; there is no job envelope, status polling, or `next` cursor.
- **Result parsing — map/scrape (verified against the server source; both decode via the shared `_decode_body`).**
  - *scrape:* the MCP result **unwraps** the REST `{success, data:{…}}` envelope — page text is top-level **`markdown`**, page URL is **`metadata.sourceURL`** (NOT `data.markdown`). Per Firecrawl's API docs `sourceURL` is the URL that was **requested**; the post-redirect URL is the separate `metadata.url` (not live-verified). `scrape_page`'s typed result carries `(url = metadata.sourceURL, text = markdown)`. A result with no non-empty `sourceURL` is a failure (M3 keys/provenances scrape evidence by URL).
  - *map:* read **`links`** — an **array of objects** `{url, title?, description?}` on current Firecrawl; extract `url` (+ `title`/`description` when present to enrich the candidate list), and **tolerate a plain-string `links` form** defensively (older servers).
- **MCP result wrapping & `structuredContent` decode.** Both servers return the payload **twice**: a `content:[{type:"text", text:<pretty JSON>}]` block **and** a native `structuredContent` object (same data). `_decode_body` prefers the structured object (read via the SDK's real attribute `structured_content`), then JSON-decodes the text block, so either wrapping yields the dict.
- **Firecrawl output shape (no connect-time probe).** M3 requires **MCP server 3.x JSON output** from Firecrawl: a JSON body (as `structuredContent` or as JSON in the text block) with top-level `markdown` and `metadata.sourceURL` for scrape, and a `links` list for map. Firecrawl MCP server 1.x and 2.x (up to 2.1.0) are reported to return raw joined text rather than JSON for scrape and never read `sourceURL`, which breaks URL keying/provenance and `_decode_body`. (This "3.x" is the MCP server package version. It is not a Firecrawl REST API version, none exists, and it is not the `/v2/` segment of the hosted URL. Source: public GitHub and docs research; not live-verified.) **A live run confirmed the hosted `/v2` endpoint returns this shape, so `open()` runs the `tools/list` capability check only — the earlier connect-time map+scrape probe is removed** (it spent two billed calls per `open()` re-confirming a verified shape). A wrong shape, if it ever recurs, surfaces as a per-call `ToolFailure(unparseable)` from `_parse_scrape_result` / `_parse_map_result` on the first real call. The `FIRECRAWL_PROBE_URL` setting and the `_decode_body` / `_parse_*` handling are kept; we do **not** rely on a declared `outputSchema`.
- **Parallel `web_search` result (verified).** The MCP result mirrors the REST payload for the fields we read — `results[]`, each with `url`, `title`, and **`excerpts` as a list of strings** — so the existing search parser (`_parse_search_result` + the `excerpts`-list fallback in `_excerpt_text`) handles it unchanged. (`usage` moves to the result's `_meta`; we don't read it.)
- **Crawl result shape (retained crawl path — not used by M3).** Handle both shapes: final data after internal polling, and a job id polled via `firecrawl_check_crawl_status`. M3's map/scrape parsers are specified above; this applies only to the retained `crawl_site` op.
- **Crawl read timeout (retained crawl path).** Crawl uses a longer timeout than search. On timeout, read the job via `firecrawl_check_crawl_status` — do not restart the crawl. Requires capturing the crawl job id. (M3 scrape uses its own per-call timeout.)
- **Concurrent calls on one Client.** One `Client` per server, shared across amenity pipelines inside the single event loop; never across threads/loops. Concurrency capped by a per-server semaphore. Every call wrapped in an explicit timeout. The session is **never** replaced or reconnected: a timeout is our side giving up on one wait, so the open session serves the next call, and a transient failure (including a dropped SSE stream) is retried by reissuing the call as a new request stream on the same `Client`. A timed-out crawl job is re-read by its id, not repeated. `scrape_pages`' fan-out shares the same `_firecrawl_sem`, so N concurrent scrapes never exceed the 2-browser limit.
- **Rate limits & concurrency.** Firecrawl is bounded on **two axes**, both as shared gateway-instance state (so one gateway paces all concurrent amenities) and **both applied to every Firecrawl call** (`firecrawl_map`, `firecrawl_scrape`, `firecrawl_crawl`): **concurrency** `FIRECRAWL_CONCURRENCY = 2` (the plan's concurrent-browser limit, `_firecrawl_sem`) **and throughput** `FIRECRAWL_RATE_PER_MINUTE = 10` (Free-plan limit, documented for `/scrape`, **per API key, shared across all team members** — a proactive token bucket over a 60 s window). In `_single_call` a Firecrawl call takes a slot **and** a token; over either limit it waits (queues on the slot / sleeps until the window refills), never dropped — so a `map_site` and a `scrape_pages` burst contend for the same 10/min. `SEARCH_CONCURRENCY = 4` (Parallel is a separate server/key, excluded from the Firecrawl bucket, reactive `429` handling only). The gateway caps its own submission concurrency and rate so it does not self-induce `429`s; the reactive `429` → `rate_limited` → 30 s, 30 s backoff stays as the backstop for the **cross-process / team-wide** slice the in-process bucket cannot see (another process on the same key). Confirm the plan's figures before raising the defaults.
- **Verification (split per server; if a test shows an issue, approach reviewed):**
  - *V2a Parallel:* ~10 concurrent `web_search` calls on one `Client`; each result matches its request; one timeout doesn't fail the others.
  - *V2b Firecrawl (M3 path):* several concurrent `scrape_page` calls on one `Client` after a `map_site`; each result matches its page; one scrape timeout doesn't fail the others; the session stays usable; `scrape_pages` is covered by the same fan-out path, and a fan-out wider than the per-minute budget is paced to ≤10/min (A7), not 429'd. (Crawl-interference checks apply only to the retained `crawl_site` path.)

## C3.1.2 — Add a Tool-Turn Call to the Shared `StructuredLLMCaller` *(client prerequisite — already built; not an R3 stage)*

**Goal.** One `StructuredLLMCaller` holds the OpenAI-then-Groq chain and serves R1 and R2. It exposes the existing structured call unchanged, plus a tool turn taking (message history, function tool definitions, `tool_choice`) and returning the assistant message with its optional `tool_calls`. Same `LLM_PROVIDER_ORDER` fallback for both calls.

**Problem.** Provider fallback is private to R1's class, so `SpecificMetricResolution` can't make LLM calls. Both provider classes build a fixed system+user pair (no history, no tool path). M3 needs a conversation where tool results are appended and re-sent. A second copy of the fallback would drift.

**Finalized approach.** Extend the provider protocol — add `generate_turn(messages, tools, tool_choice)` to `StructuredLLMProvider` and both provider classes. The caller loops over providers for either method.

**Decisions — generally mandatory**
- **Ownership.** Built once at the composition root, passed to R1 and `SpecificMetricResolution`. Created and closed once.
- **Fallback rule.** Fallback on `LLMProviderError` — a truncated response (cut short by the token limit) and a **non-decodable** body (empty / not JSON / not a JSON object) both count, because the provider did not actually produce a usable body. A **returned, decodable, schema-valid body** is a provider success; its schema contents never trigger fallback. (A structured turn additionally falls back on an OpenAI `refusal` or a non-`stop` `finish_reason` — see the strict-mode rule below.)
- **Strict mode guarantees schema validity (structured turns).** Structured turns (`call_structured` — triage, resolution) use constrained decoding: both providers send `response_format` with `strict: true`, and the configured models support it (OpenAI strict models; Groq `openai/gpt-oss-120b`, with `gpt-oss-20b` the other strict-capable option). A decodable-but-schema-invalid body therefore **cannot occur**, so there is **no schema retry and no schema-driven fallback**. Per-call validation is `refusal` → `finish_reason` → defensive parse: a populated OpenAI `refusal` field is a decline → fall back to the other provider, and if it also declines the amenity's metrics end **unresolved** (D5); `finish_reason` of `length` (truncation) or a non-`stop` / `content_filter` stop is an `LLMProviderError` → fallback; the body is then parsed with its Pydantic model as a **defensive backstop** — under strict this always passes, so a parse failure is an unexpected provider anomaly that falls back (raising `MetricResolutionProviderError` if every provider is exhausted), **never a same-provider retry**. Semantic non-conformance (per-metric `enum` / `unit` / `value_type`, the `verification` gate — the R3.M2.3 code checks) is unchanged: a genuine resolution outcome (`null` / verification-failed), never a provider error.
- **Config caveat (strict-capability).** This guarantee holds only while both models stay strict-capable. Pointing `GROQ_EXTRACTION_MODEL` at a non-strict-supporting model drops Groq to **best-effort** mode, which may `400` (→ fallback) or return **syntactically valid but schema-invalid** JSON — reopening the schema-retry question this decision closes. Changing the structured model must revisit this rule.
- **Typed error.** An M3 call — tool turn (`call_turn`) or structured turn (`call_structured`) — raises `MetricResolutionProviderError` when every provider in the chain fails to return a usable response. The error carries `stage` (the M3 step that made the call) and a required **`cause`** (prerequisite change — see Prerequisites):
  - `availability` — **every** provider in the chain failed with a timeout, a 5xx, a connection error, or a 429 after its retries ran out.
  - `content` — **at least one** provider failed with a `refusal`, an abnormal `finish_reason`, or the defensive-parse anomaly above. A chain with mixed causes is `content`: one provider rejecting the request on content grounds means the failure is about this request, not an outage.
  - `circuit_open` — the run-level circuit breaker (R3.M1.5) was open, so no call was made. Raised by the M3 caller-side breaker check, never by a provider.
  Only `availability` counts toward the circuit breaker. `MetricResolutionValidationError` is **not** raised here; it belongs to R3.M1.1 (tool-argument validation, the genuinely non-strict path). R1 keeps its own error behavior.
- **Regression.** R1 behavior unchanged; a test covers the lifted helper against existing R1 cases.

**Decisions — problem-specific**
- **Message format.** OpenAI chat format (Groq-compatible), provider-neutral, so a fallback provider receives the same messages including prior `tool_calls` and `tool` messages with `tool_call_id`s.
- **No `strict` on function tools.** Groq doesn't support it → arguments validated in code (R3.M1.1).
- **Two request modes, never combined (tool turn vs structured turn).** A request is **either** tools-only **or** schema-only — the two are never merged. `call_turn` sends `tools` + `tool_choice` and **no `response_format`**; `call_structured` sends a strict `response_format` schema and **no `tools`**. *When* each mode fires and *what it reads* are owned elsewhere — structured turns are invoked by triage (R3.M1.4) and resolution (R3.M2.2), which resolve from the per-metric evidence store (`metrics_source_content`), not this caller's message thread; C3.1.2 guarantees only the mode separation. This invariant makes the former open question — *does a provider accept `tools` and `response_format` in one request?* — **moot by construction**: the plan never issues such a request, so it never depends on the answer.
- **Parallel calls.** `parallel_tool_calls` stays on.
- **Truncated tool calls.** `finish_reason: length` with partial tool args → provider failure, not executed.

## R3.M1.1 — Build the Phase-Scoped Tool Catalog and Call Guard

**Goal.** Per phase, the LLM receives only the valid tools: `web_search` in phase 1, `firecrawl_map` then `firecrawl_scrape` in phase 2. Every returned tool call passes a guard before reaching the gateway: checks name, validates args (incl. the scrape `id` and its required `metric_label`), dedups and caps Phase-2 scrapes, attributes the call to its metric(s), and sets every application-controlled argument.

**Problem.** MCP schemas let the caller set fields the app must control (the scrape/map `url`, scrape `formats`, etc.). Phase order is app-enforced; an instruction alone won't stop a wrong-phase call, and a wrong-phase / out-of-catalog call left in the replayed history breaks the next Groq request (see Guard failure handling). Evidence must be attributed to a metric (the `web_search` / `firecrawl_scrape` schemas have no metric field). Groq doesn't enforce function arg schemas → validate in code.

**Finalized approach.** Derived schemas with controlled fields removed — function schemas built from MCP schemas, application-controlled fields removed from the exposed schema. Code injects those fields and adds `metric_label`.

### Steps of sub-component

#### 1. Build LLM-Facing Tool Catalog

Reusable R3.M1.1 abstraction that builds an LLM-facing tool catalog for the caller's current workflow context. Any workflow caller preparing a tool turn can use it; it is not limited to website discovery or `web_search`. Application-owned context selects the permitted tools and schema policy. The step builds schemas, not search argument values, and does not call the LLM or execute tools.

**First usage context — website discovery.** R3.M1.5 coordinates discovery; R3.M1.3 calls this abstraction when an existing website is missing or unsuitable. The discovery example below illustrates the shared abstraction using `website_discovery`; later evidence contexts use the same abstraction with their own tool and field policies.

##### Input params

| Param name | Format / type | Source and purpose |
|---|---|---|
| `raw_tool_definitions` | `dict[str, dict[str, RawToolDefinition]]`, keyed first by application-owned server key (`parallel`, `firecrawl`), then by MCP tool name. Each definition contains `name: str`, `description: str \| None`, and `input_schema: dict[str, Any]` holding the complete JSON Schema. | C3.1.1 retrieves definitions through `tools/list` during `open()` and exposes them through the planned gateway interface. The workflow orchestrator stores them in workflow state as `raw_tool_definitions` before discovery starts. The current caller reads that state and passes the definitions. Must include the server/tool pair required by the selected context (`parallel` / `web_search` for discovery); these are complete schemas, not merely sets of argument names. |
| `context` | Application-owned enum or literal union: `website_discovery`, `metric_web_search`, `site_map`, `metric_scrape`. | Selected by the caller according to workflow progress: R3.M1.3 supplies `website_discovery`; R3.M1.4 supplies the appropriate evidence context. Selects the allowed tool set and field policy. MCP and the LLM do not choose this value. |

`RawToolDefinition`, the context type, and the workflow-state field above define the required contract; their concrete implementation is to be added. Definitions are fetched once per gateway session and reused. Preserve server grouping in workflow state; do not flatten definitions or fall back to a different server. The context policy selects both server and tool. For discovery, read `raw_tool_definitions["parallel"]["web_search"]`; a missing selected server or tool is an explicit catalog-construction failure. In the discovery context, amenity identity, address, actual queries, official URL, metric labels, and conversation history are not inputs to catalog construction. R3.M1.3 supplies amenity identity and search instructions separately when constructing the subsequent LLM request. Candidate-ID and metric-label membership checks belong to the separate guard step.

| Context | Selected server / tool | LLM-facing field policy |
|---|---|---|
| `website_discovery` | `parallel` / `web_search` | `objective`, `search_queries`; no `metric_label`. |
| `metric_web_search` | `parallel` / `web_search` | `objective`, `search_queries`, `metric_label`. |
| `site_map` | `firecrawl` / `firecrawl_map` | No LLM-settable arguments; homepage URL is injected after admission. |
| `metric_scrape` | `firecrawl` / `firecrawl_scrape` | Candidate `id` and required `metric_label`(s); URL and scrape settings remain application-owned. |

##### Process flow of step

```text
BUILD LLM-FACING TOOL CATALOG — R3.M1.1
Example invocation: website discovery
══════════════════════════════════════════════════════════════════════════

 BEFORE — workflow setup and R3.M1.3 discovery decision
 ────────────────────────────────────────────────────────────────────────
 C3.1.1 opens → retrieves and exposes complete raw MCP definitions.
 Workflow orchestrator stores definitions in workflow state.
 R3.M1.3 determines that the existing website is missing or unsuitable.
 It reads the definitions and selects context = website_discovery.
   │
   │ Inputs: raw_tool_definitions + context=website_discovery
   ▼
 ┌─ REUSABLE CATALOG BUILDER — R3.M1.1 ──────────────────────────────────┐
 │                                                                      │
 │  1. Select server + tool using the supplied context policy.           │
 │     For website_discovery: parallel → web_search only.                │
 │     Missing server/tool → report a catalog-construction failure;     │
 │     do not use another server, invent a schema, or ask the LLM.       │
 │                                                                      │
 │  2. Derive a restricted copy of its input schema.                     │
 │     Preserve relevant field types and descriptions.                  │
 │     Preserve retained fields' $ref references and the $defs they     │
 │     depend on, including transitive dependencies. Do not inline     │
 │     referenced definitions. Validate that references resolve; fail   │
 │     catalog construction explicitly if they cannot be preserved.    │
 │     Apply the context's field policy. For discovery:                 │
 │     expose objective + search_queries as required arguments.         │
 │     Require at least one search query; disallow extra arguments.     │
 │     Omit application-controlled fields; do not add metric_label.     │
 │     Leave the raw definition in workflow state unchanged.            │
 │                                                                      │
 │  3. Adapt to C3.1.2's function-tool format:                            │
 │     type = function                                                  │
 │     function = {name, description, parameters: restricted schema}     │
 │                                                                      │
 │  4. Return the selected, restricted function-tool definitions.        │
 │     In this example: a list containing only web_search.              │
 └──────────────────────────────────────────────────────────────────────┘
   │
   │ Output: tool_catalog: list[dict[str, Any]]
   ▼
 R3.M1.3 receives the catalog.
 It passes the catalog as tools to C3.1.2's call_turn(), alongside
 separately constructed messages and the other caller parameters.

 EXIT — catalog construction is complete.
 The LLM generates actual argument values in the subsequent tool turn.
 Guarding those proposed calls is a separate R3.M1.1 step.
```

##### Agreed decisions for the traceflow

| Decision | Agreed rule |
|---|---|
| How to restrict fields | Use an explicit allowlist per context. For discovery: only `objective` and `search_queries`. |
| What to preserve | Preserve permitted fields' types, descriptions, and compatible constraints. Apply application rules explicitly. |
| What if the raw schema conflicts with our expectations? | Fail catalog construction before making an LLM call, with a clear error—for example, if `search_queries` is missing or has a type incompatible with the guard or execution interface. Do not silently invent a replacement schema. |
| How to handle schema dependencies | Preserve references needed by retained fields and their required `$defs`, including transitive dependencies; do not inline referenced definitions. Remove schema references or requirements that depend on excluded fields, where safe. Validate that retained references resolve. If safe transformation or reference preservation is unsupported, fail explicitly before making an LLM call. |
| What counts as a valid query? | Require at least one string through the discovery schema. Do not introduce blank-string or whitespace-only checks. The generic guard validates the offered schema without modifying values. |

For every context, the output is the Chat Completions function-tool list already accepted by C3.1.2 (`tools: list[dict]`), not the raw MCP definition format. Its selected tools and schemas vary by context. The discovery catalog (catalog of websearch for website discovery) has no `metric_label`; the metric-label requirements below apply to metric evidence acquisition.

#### Guard Proposed Calls

Reusable Step 2 of R3.M1.1. Validate the entire LLM tool-call message against the exact catalog supplied for that turn and applicable application checks. Tool names, schemas, and additional validators are supplied separately; the guard is not specific to website discovery or any particular tool.

Accept only a message containing at least one call where every call passes. Any validation error rejects the entire message; no valid sibling calls are admitted independently.

##### Input params

| Param name | Format / type | Source and purpose |
|---|---|---|
| `proposed_tool_calls` | Ordered sequence of calls with `id`, tool `name`, and `arguments` as a JSON string. | Extracted from the assistant response returned through C3.1.2 and passed by the caller. Empty sequences are rejected. |
| `tool_catalog` | `list[dict[str, Any]]` in C3.1.2 function-tool format. | Exact catalog offered for this turn; defines permitted tool names and argument schemas. Raw MCP definitions are not needed again. |
| `context` | Application-owned context value; always supplied. | Caller selects the context used to choose applicable additional validators. |
| `validation_context` | Caller-provided runtime reference data or `None`. | Supplies facts for additional validators. `None` skips checks requiring that data; an empty dictionary is supplied data, not `None`. |

Tool name and call ID are outer call fields, not arguments. Field nesting follows the response adapter's format. Each call needs a unique tool-call ID within the message, even when several calls use the same tool.

##### Process flow of step

```text
GUARD PROPOSED CALLS — R3.M1.1
══════════════════════════════════════════════════════════════════════

 BEFORE
 Build LLM-Facing Tool Catalog produced the offered catalog.
 The caller supplied it through C3.1.2 and received the response.
 No proposed call has executed.
   |
   | proposed_tool_calls + tool_catalog + context + validation_context
   v
 +-- GENERIC CALL GUARD --------------------------------------------+
 | 1. No calls: record no_tool_calls (category: null).               |
 | 2. Check required outer fields and unique tool-call IDs.         |
 |    Missing fields / duplicate IDs: invalid_call_structure.       |
 | 3. Match tool name exactly against the supplied catalog.         |
 |    Tool absent: out_of_catalog.                                 |
 | 4. Decode each permitted tool's argument JSON string.            |
 |    Malformed JSON: in_catalog / invalid_argument_json.           |
 | 5. Validate decoded arguments against that tool's schema.        |
 |    Schema failure: in_catalog.                                  |
 | 6. If validation_context is not None, invoke the applicable      |
 |    separate tool validator after prerequisite checks pass.      |
 |    Application-validation failure: in_catalog.                  |
 | 7. Collect all detectable errors across all calls.               |
 |    Dependent checks require successful prerequisites.           |
 |    Preserve identifiers where available and argument values.    |
 | 8. Any error: REJECT entire message; admit no calls.             |
 |    At least one call and no errors: ACCEPT all calls in order.   |
 +----------------------------------------------------------------+
   |
   +-- REJECTED -> Step 3: Prepare rejection outcomes
   |              Step 4: Sanitize replay history, where required
   +-- ACCEPTED -> Step 5: Prepare admitted tool calls

 EXIT: no tool execution, history mutation, or retry decisions.
```

##### Agreed decisions for the traceflow — critical decision factors

| Decision factor | Agreed rule |
|---|---|
| Authoritative catalog | Use the exact catalog offered for the turn. Match names exactly; infer no aliases and hardcode no tools. |
| Call structure and identity | Missing required outer fields, including names or IDs, and duplicate tool-call IDs produce `invalid_call_structure`. Use call position when IDs are missing or ambiguous. |
| Argument decoding | Arguments consistently arrive as JSON strings. Decode before validation. For a permitted tool, malformed JSON produces `in_catalog` with reason `invalid_argument_json`. |
| Schema validation | Each tool's supplied schema determines required fields, allowed fields, types, and decoded argument structure. Do not hardcode argument names or silently repair or coerce values. |
| Blank strings | No dedicated empty-string or whitespace-only checks; remove the previously proposed blank-objective and blank-query checks. |
| Normalization | Preserve accepted values; do not trim, deduplicate, or otherwise normalize arguments. |
| Additional limits | Introduce no separate query-count, text-length, or call-count policy here. Validate the supplied schema as offered. |
| Multiple calls and empty messages | Accept only a nonempty message whose calls all pass. Any error or no calls rejects the entire message; no sibling calls proceed. |
| Rejection classification | Absent tool: `out_of_catalog`. Permitted tool's decoding, schema, or application-validation failure: `in_catalog`. Missing outer fields or duplicate IDs: `invalid_call_structure`. No calls: category `null`. |
| Error reporting | Collect all detectable errors, not only the first; continue inspecting other calls. Skip checks whose prerequisites failed. Step 3 constructs rejection outcomes. |
| Validation authority | Caller always supplies `context`. Separate tool validators interpret optional runtime `validation_context`; select by tool name and context as needed. `None` skips data-dependent checks. |
| Execution readiness | Passing means satisfying the offered schema and applicable application checks. Gateway availability and execution failures remain downstream concerns. |

##### Additional validator contract

```python
validate(arguments, validation_context) -> list[ValidationIssue]
```

Select a separate validator by tool name and context as applicable. Invoke it when `validation_context` is not `None` and prerequisites pass. An empty returned list means success; returned issues become `in_catalog` errors with call metadata attached by the guard. A tool needing no additional checks requires no custom validator. Schemas check structure and types; separate validators can check values against caller-provided runtime facts such as available identifiers. These examples are not built-in guard requirements.

##### Output and error contract

Return one message-level decision:

| Decision | Returned information |
|---|---|
| `accepted` | `validated_calls`: all calls in original order, each containing `tool_call_id`, `tool_name`, and decoded, validated `arguments`; `errors: []`. |
| `rejected` | `validated_calls: []`; `errors`: all detected validation failures. No calls admitted. |

Decoded and validated describe the same returned arguments object, not separate fields.

| Error field | Meaning |
|---|---|
| `reason_code` | Stable failure identifier, e.g. `invalid_argument_json` or `no_tool_calls`. |
| `explanation` | Concise readable description. |
| `call_index` | Zero-based call position; `null` for message-level errors. |
| `tool_call_id` | ID where available; otherwise `null`. |
| `tool_name` | Name where available; otherwise `null`. |
| `category` | `out_of_catalog`, `in_catalog`, or `invalid_call_structure`; `null` for no calls. |
| `field_path` | Error location where applicable, e.g. `arguments.candidate_id`; otherwise `null`. |

Schema validators provide error locations; separate validators explicitly return locations for their issues. Do not infer paths from explanation text. Call position disambiguates missing or duplicate IDs. An empty-call error uses `reason_code: "no_tool_calls"` with call fields, category, and field path set to `null`.

```json
{
  "decision": "rejected",
  "validated_calls": [],
  "errors": [{
    "reason_code": "invalid_argument_type",
    "explanation": "candidate_id must be a string.",
    "call_index": 0,
    "tool_call_id": "call_123",
    "tool_name": "example_tool",
    "category": "in_catalog",
    "field_path": "arguments.candidate_id"
  }]
}
```

##### Immediately preceding step and downstream ownership

Build LLM-Facing Tool Catalog precedes this step. The caller sends that catalog and its instructions through C3.1.2, then supplies the response's proposed calls and the same catalog to this guard. Step 3 builds rejection outcomes; Step 4 performs required replay cleanup; Step 5 prepares tool calls only after whole-message acceptance. The guard does not construct final tool error messages, mutate history, inject execution arguments, execute tools, or decide retries.

This Step 2 contract supersedes older per-call admission, blank-query, and normalization/cap responsibilities attributed to the guard. Existing execution budgets and application-controlled argument preparation belong to surrounding orchestration or later preparation, not this generic validation step. History handling for structural errors without usable unique IDs must be specified in the downstream steps; do not invent matching IDs here.

**Decisions — generally mandatory**

Status labels identify changes resulting from the finalized catalog-building and guard steps. **Unchanged** highlights existing policies unaffected by those steps.

- **Updated — Catalog construction and validation authority.** Build a restricted copy of the raw MCP schema using an explicit field allowlist selected by application-owned context. Preserve permitted types, descriptions, compatible constraints, and required references with their transitive `$defs`; do not inline definitions or mutate the raw schema. Fail before the LLM call if the selected server/tool is missing or the schema cannot be safely transformed. Return C3.1.2-compatible function tools. The guard uses the exact catalog offered for that turn, matches names exactly, and does not need raw definitions again. Context-specific field lists are recorded below.
- **Added — Generic guard contract.** Require a nonempty tool-call message with required outer fields and unique call IDs. Decode argument JSON strings and validate against each offered schema without coercion, repair, normalization, dedicated blank-string checks, or additional limits. Collect all detectable errors, skipping dependent checks when prerequisites fail. Accept all calls in original order only if every call passes; otherwise reject the entire message and return no admitted calls. Report stable reasons, available call metadata, call positions, and explicit field paths. Missing fields or duplicate IDs are `invalid_call_structure`; no calls produces `no_tool_calls` with category `null`.
- **Added — Additional validation and ownership.** The caller always supplies `context`. Separate validators selected by tool and context check runtime facts when `validation_context` is not `None` and prerequisites pass; an empty dictionary is supplied data. `None` skips data-dependent checks. The guard returns decisions only. Step 3 constructs rejection outcomes, Step 4 sanitizes replay history, and Step 5 prepares admitted calls. Execution argument injection, deduplication, execution ceilings, gateway execution, and retry decisions belong downstream or to orchestration.
- **Updated — Guard failure handling.** Any validation error rejects the whole message, including otherwise valid sibling calls; none reaches the gateway or consumes a gateway-call cap. Step 3 must prepare matching outcomes for calls with usable unique IDs, including siblings withheld by message rejection. Handling structural errors without usable unique IDs and empty messages remains to be specified downstream; do not invent IDs or misclassify valid siblings as argument failures. Existing workflow retry allowances remain caller-owned, and the guard does not assign per-metric retries for malformed or mixed messages. For identifiable rejected calls, preserve the distinction:
  - *In-catalog rejection* — decoding, schema, or applicable application-validation failure for an exposed tool. Preserve the assistant call and its paired error response in replay history.
  - *Out-of-catalog rejection* — a tool absent from the exact offered catalog. Step 4 removes that call and its paired response before replay, preserving unrelated messages. This retains the existing Groq compatibility policy for both providers.
- **Unchanged — Unexposed tools.** MCP tools outside the selected context's allowlist remain unexposed. `firecrawl_crawl` is retained in the gateway but never exposed to the LLM.

**Decisions — problem-specific**
- **Updated — LLM-settable fields by context.** `website_discovery` selects `parallel` / `web_search` and exposes only required `objective` and `search_queries`, with at least one string query and no additional arguments; it has no `metric_label`. `metric_web_search` exposes `objective`, `search_queries`, and `metric_label`. `site_map` selects `firecrawl_map` with no LLM-settable arguments. `metric_scrape` selects `firecrawl_scrape` with candidate `id` and required `metric_label`(s), allowing multiple labels; URL and scrape settings remain application-owned. Discovery catalog construction takes raw definitions and context, not amenity identity, queries, labels, or history.
- **Updated — Query rules in the tool description.** Concise related keyword queries 3–6 words, ≥1 per call, 2–3 diverse recommended, operators allowed. The guard enforces the offered schema's minimum of one string query. Word count and diversity remain instructions; introduce no dedicated blank-objective or blank-query checks and do not trim or deduplicate accepted values.
- **Updated — `metric_label` rule.** Applies to metric evidence contexts only, never website discovery. Required label structure is expressed in the offered schema. A separate validator checks membership in the amenity's metric set using caller-supplied runtime data; an invalid label rejects the entire message. Under the generic contract, `validation_context=None` skips this data-dependent check, so callers requiring membership validation must supply that data. Labels are removed during admitted-call preparation before MCP execution.
- **Unchanged — Scrape / map clamps (map→scrape model).** `firecrawl_map`'s `url` is **app-injected** (the resolved official homepage from `website_search_results`, R3.M1.3). `firecrawl_scrape`'s `url` is **app-resolved from the LLM's `id`** against the map candidate list. The LLM supplies **no** URL in either tool, so the draft's host-clamp (host normalization / netloc comparison) is **removed** — there is no LLM-supplied host to validate. The LLM decides *when* to scrape and *which page* (by `id`, D1) and tags each scrape with its `metric_label`(s); the app fills everything else.
- **Updated — Caps and preparation ownership; budget values unchanged.** The phase loop (R3.M1.4) enforces attempt budgets. The guard validates required label structure through the schema and candidate/label membership through supplied additional validators; URL resolution, URL deduplication, and the 8-distinct-scrape ceiling belong to downstream preparation/orchestration. The cap counts only MCP calls that hit the gateway. Phase 1: one `web_search` + one retry per metric. Phase 2: one `firecrawl_map` (+ one retry), then **one `firecrawl_scrape` per phase-2-eligible (unresolved + `factual`) metric, deduped by URL to ≤ 8 distinct scrapes per amenity**, each scrape + one retry. Retry allowed only when attempt 1 failed, timed out, or was guard-rejected, subject to caller attribution of the rejected message. A successful attempt 1 is not retried even if metrics remain unresolved. Worst case bounded: ≤2 gateway searches per metric; ≤ (1 map + 8 scrapes) × 2 gateway Firecrawl calls per amenity; a rejected message consumes neither gateway budget. The generic guard introduces no separate call-count limit.
- **Unchanged — Phase 2 availability.** The `firecrawl_map` / `firecrawl_scrape` tools are offered only when a URL exists AND ≥1 metric is unresolved.

## R3.M1.2 — Shape Tool Results

**Goal.** Every tool call becomes exactly one `tool` message carrying status `ok` / `empty` / `failed` plus the tool's result — never an exception, never an absence. Operating on the gateway's already-resolved outcome, classify in fixed order: confirm clean termination first, only then check content presence (`ok`) or absence (`empty`); anything the gateway marks as not cleanly terminated is `failed`. The result is always passed through alongside its status.

**Problem.** The loop requires exactly one `tool` message per call — a failed/empty/exception call can't be an absence (dangling tool call malforms the next turn). `empty` vs `failed` demand different reactions and must not collapse: `failed` justifies the one retry; `empty` is final and must not consume it. They also carry different meaning to R3.M2: `empty` → confident `no_evidence`; `failed` → tool-failure reason. `empty` must never be assigned to a call that didn't genuinely finish with nothing.

**Finalized approach.** Status-signal first, content second (ordered guard). On the resolved outcome: first "did it terminate cleanly?" (error / `is_error` / gateway-marked failure → `failed`); only on confirmed clean termination, "is there content?" (→ `ok` with result, or `empty`). Same guard for every tool; result always passed through.

**Decisions — generally mandatory**
- **Outcome form.** Every tool call → exactly one `tool` message with status + result. Never an exception, never an absence.
- **Ordered guard: termination before content.** The content check is unreachable until clean termination is confirmed — this guarantees `empty` is only ever a genuinely-contentless call.
- **Termination signal is the sole source of `failed`.** Error / `is_error` / gateway-marked failure → `failed` at stage one, regardless of any partial/blank payload. Payload content never influences `failed`.
- **Retry alignment.** `failed` is eligible for the metric's single budget retry; `empty` is terminal and consumes none. (Retry eligibility and attempts are owned by the R3.M1.4 loop — the LLM re-emits the call, the loop enforces the limit; this component only supplies the gating status.)

**Decisions — problem-specific**
- **Operates only on a resolved outcome.** No MCP call, no job polling, no waiting — all call mechanics (incl. driving a polled crawl to completion) belong to the gateway (C3.1.1).
- **Result always passed through.** Status is a label, not a filter; content never stripped/withheld/interpreted. What to do with empty/failed is the consumer's decision.
- **Depends on the gateway distinguishing "finished empty" from "never finished."** A timed-out / never-arrived call must arrive here already marked a failure, not an empty payload. The "exhausted/unknown → `failed`, not `empty`" guarantee is a requirement on the gateway's output.
- **Status meaning carried to R3.M2.** `empty` → confident `no_evidence`; `failed` → tool-failure reason.

## R3.M1.3 — Resolve the Official Website URL Before the Loop

**Goal.** Before the LLM loop runs, produce a resolved `website_search_results` object per work item holding `website_url` and `website_origin` (`google` / `discovered` / `none`). If `PredefinedMetricsRecord.website` is set **and passes the official-URL gate** (`official_url_gate`, below), use it (`origin=google`). Otherwise one discovery step runs → a confirmed official site (`origin=discovered`) or `none`. `PredefinedMetricsRecord.website` is never changed.

**Problem.** Google's `websiteUri` is sometimes absent, and is sometimes a social/aggregator host rather than the official site. Phase 2 needs an official URL to crawl. RC8 requires URL-first. A wrong site produces wrong crawl evidence.

**Finalized approach — gate-first, then Approach 2 (one search, LLM selection).**
Discovery is a **self-contained prerequisite step, not a phase.** It does not share the phase loop's budget, triage, or machinery; it runs to completion before any amenity loop starts and produces an input to it. Per work item it is a **two-stage decision** — the gate first, the search only when the gate declines:

**Stage 0 — official-URL gate (deterministic; no LLM, no search).** Run `official_url_gate` (the `tldextract` SLD-match specified under "Google-provided URL handling" below) on the candidate Google `website`. Returns `official` → `website_url = website`, `website_origin = google`, and **discovery stops here (no search runs)**; returns `discovery` → fall through to Stage 1. This is the common, zero-cost path and the only place `origin=google` is produced. Stage 0 is executed as a **synchronous pre-pass over all work items** before the discovery fan-out (see "Batch orchestration"), so gate-passing items never enter the async batch.

**Stage 1 — one search + LLM selection (only when Stage 0 returns `discovery`).**
1. **Tool turn** exposing *only* `web_search` — the **LLM builds the search args** and makes the call through the gateway (the one place in the flow where the LLM chooses the search arguments). The amenity identity (name, locality) is given to the LLM as the matching target; the **complete `address` string is passed to the LLM verbatim** and the instruction directs it to **use only the postal code** from that address to scope the query to the target locality — the app parses nothing.
   - **Input source (finalized).** All discovery inputs are read from the work item's **`PredefinedMetricsRecord`** — the M1 record at `state.predefined_records[category_id][place_id]` (looked up by the work item's `(category_id, place_id)`; the work item itself carries only the key, not these fields). The fields used: **`name`** and **`website`** (the candidate Google `websiteUri`, consumed by Stage 0), plus the **full `address`** string, passed to the LLM **verbatim** (the app does not parse locality or postal code — the instruction tells the LLM to use only the postal code for locality scoping). No other object is read for discovery.
2. **Structured selection turn** (`response_format`, no tools). To make a hallucinated URL **structurally impossible**, the selection uses **candidate id-indirection** (full mechanism under "Candidate id-indirection & verdict validation" below): after the search returns, the app indexes each result URL under an opaque `id`, shows the LLM `id + title + snippet`, and the LLM returns a single **candidate `id`** (→ the app resolves `id → url`, `website_origin = discovered`) or a **`none` sentinel** (→ `website_origin = none`). **The LLM never emits a URL.** It judges each candidate's snippet against the **amenity identity it was given** (name, locality, and the amenity's own `address`); the raw results carry no structured **per-candidate** address or phone — only URL + snippet — which is why the draft's "address/phone agreement" acceptance rule was dropped.

Stage 0 is pure code (stdlib `urlsplit` + pinned `tldextract`), so it adds no LLM/gateway cost. Stage 1, because it switches from code-built to LLM-built args + a structured verdict, depends on **C3.1.2** (tool turn) and **R3.M1.1** (the tool-call guard, which validates the `web_search` tool turn — **not** the selection verdict) and needs a small schema (à la R3.M2.1 — returning a `selected_id` / `none`, not a URL), in addition to **C3.1.1** (gateway).

**Host rule — binary.** An **official first-party site** → `website_url` + eligible for crawl. **Everything else** (social, aggregator, directory/listing, maps, review) → `none`, **no crawl**. There is no middle "aggregator → crawl anyway" class. This makes phase-1 query scoping always safe, since a non-null `website_url` is always an official site. The instruction's one judgment: *"is this the amenity's own first-party official site? If not, return `none`."*

**Google-provided URL handling — finalized gate (`official_url_gate`, `tldextract`-based).** The trust rule is **revised** from the draft's "use as-is, not re-checked": a Google `websiteUri` is trusted **only when a cheap, deterministic gate confirms it by rule**. The gate runs **before** any discovery search and returns `official` (trust → `website_url = website`, `website_origin = google`, no search) or `discovery` (run the search + LLM selection).

**Core idea.** Match the brand name against the **SLD label only** (the label left of the public suffix), ignoring subdomain and suffix. That single choice decides the expensive direction by rule: `brand.evil.com` → `discovery` (SLD `evil`), while a buried official site `clinic.reseller.greenvalleydental.co.uk` → `official` (SLD `greenvalleydental`).

Ordered steps (order matters):

```
0 PRESENCE   website empty / whitespace                          → DISCOVERY
1 HOST       urlsplit(website).netloc → lower, strip userinfo/port, rstrip('.')
2 EXTRACT    sub, sld, suffix = extractor(host)
             no sld or no suffix (IP, localhost, bare host)       → DISCOVERY
             registered_domain = f"{sld}.{suffix}"
3 DENYLIST   registered_domain ∈ DENYLIST  (exact set membership) → DISCOVERY   (fast reject)
4 SLD MATCH  match(compact(name), compact(sld))                   → OFFICIAL(origin=google)
5 ELSE                                                            → DISCOVERY
```

- **`DENYLIST`** — exact-set membership on `registered_domain` (no `endswith`/substring), e.g. `yelp.com`, `business.site`, social / maps hosts. A **fast-reject optimization only**, no longer load-bearing for correctness: step 4 already rejects foreign SLDs by rule.
- **`compact(x)`** = NFKD → drop combining marks → casefold → keep `[a-z0-9]` (NFKD, not NFKC, so accents **fold** instead of being deleted): `"Café México"` → `cafemexico`.
- **`match(cn, cs)`** = both `≥ MIN_LEN` (5) **and** (`cn in cs` **or** `cs in cn`). The bidirectional substring absorbs a domain carrying an extra token (`greenvalleydentalclinic`) or dropping a generic one; the length guard blocks spurious short hits.

**Library configuration (locked).** *Pinned, offline PSL* — one module-level `TLDExtract(cache_dir=<vendored snapshot>, suffix_list_urls=[])` so it **never fetches the PSL at runtime** (deterministic, reproducible tests, no network dependency); refreshing the snapshot is a deliberate maintenance task. *`include_psl_private_domains=True`* — recognizes brand-owned platform subdomains (`brand.wixsite.com`, `brand.github.io`) as the brand's own SLD → `official`, while still rejecting foreign apex domains (`brand.evil.com` → SLD `evil`); private suffixes cover only delegated platforms and do **not** reopen the `evil.com` leak. (Set `False` to send all site-builder subdomains to `discovery` — a cheaper, more conservative false-negative; recommendation is `True`.)

**Why strict (asymmetry).** A false `official` skips discovery and feeds a wrong site to the crawl (expensive, uncorrectable); a false `discovery` is cheap and usually re-finds the URL. So the SLD rule is precise on the OFFICIAL direction, and anything ambiguous falls to `discovery`.

**Residual risk & maintenance.** *Accepted false-negatives (cheap):* creative/acronym domains (`smile-dds.com`, `nyu.edu`) → `discovery` → LLM backstop. *Accepted false-positive (now tiny):* a non-denylisted registrable domain whose **SLD itself** matches the brand but isn't theirs (a deliberate decoy `greenvalleydental.<tld>`) — no no-fetch gate can catch that, far rarer than v1's leak. *Maintenance:* `tldextract==<pin>` in the dependency manifest, a vendored PSL snapshot, and a periodic refresh step. (This reopens the draft's locked "trust as-is" rule — intentional.)

**Decisions — generally mandatory**
- **LLM provider failure and the circuit breaker (R3.M1.5).** A `MetricResolutionProviderError` from discovery's tool turn or selection turn gives the work item a `none` result; the amenity still runs (phase 1 without a URL, no phase 2). The amenity-level "end the amenity" rule (R3.M1.4 Failure handling) does **not** apply to discovery. A `cause = availability` failure from either discovery LLM call increments the run's breaker counter, and a successful discovery LLM call resets it to 0. Before a discovery coroutine starts Stage 1, it checks `breaker_open`: when open, the work item skips its search and selection turn and gets a `none` result.
- **Failure vs empty (mirrors R3.M1.2).** *Tool call failed* (gateway failure) → one retry, then `none`. *Search returned results but the LLM chose the `none` sentinel* → terminal `none`, **no retry** (a confident decision). *Invalid verdict* — schema-invalid, **or** a `selected_id` not in the issued candidate set (see "Candidate id-indirection & verdict validation") — → treated as **failed → one retry** of the **selection turn only** (re-send the same indexed candidates already in hand; no second `web_search`); still invalid → terminal `none`. This same-provider retry is distinct from R3.M2.2's provider-level fallback.
- **Budget.** The discovery `web_search` is one real gateway call; it does **not** consume any metric's phase-1 attempt or the amenity's crawl retry. It runs under the Parallel search semaphore; its selection turn runs under the LLM-call bound.
- **Where the result lives.** The resolved verdict (`website_url`, `website_origin`) is persisted to the `website_search_results` object, keyed `(category_id, place_id)`. The **full indexed candidate set** is persisted separately to `state.discovery_search_results` for evaluation (see "Store candidates for evaluation"). Downstream (phase-1 `web_search`, phase-2 `firecrawl_map`) reads the URL from `website_search_results` as read-only context.

**Decisions — problem-specific**
- **Precision over recall.** An unconfirmed candidate → `none`. The LLM **cannot** invent a URL — it selects a candidate `id` and the app resolves it to a real search-result URL (see "Candidate id-indirection & verdict validation"); invention is prevented **by construction**, not merely instructed.
- **Candidate id-indirection & verdict validation (anti-hallucination).** The selection turn is the only point where the LLM would otherwise emit a website URL; a shape-valid but **hallucinated** URL would pass a type check, become `website_url`, scope phase-1 queries, and be **app-injected as the phase-2 `firecrawl_map` url** — crawling a nonexistent host (expensive, uncorrectable, and recurring given LLM non-determinism). Mechanism, mirroring R3.M1.1's phase-2 scrape id-indirection but adapted to a single pick:
  1. **Candidate indexing** — after `search_web` returns a `WebSearchResult`, the app iterates `.excerpts`, **drops hits with `url is None`** (non-selectable), assigns a fresh opaque `id` (`c1…cN`) to each remaining hit, and builds `candidates` (`id + url + title + text`) plus an app-only **`id → url` map**.
  2. **Selection turn** — the LLM is shown `candidates` (ids + title + snippet; `url` shown only for judgment) and the schema returns a single **`selected_id`** or a **`none` sentinel** — never a URL.
  3. **Verdict validation + resolve** — a **body-level check in R3.M1.3's validation path** (explicitly **not** the R3.M1.1 tool-call guard, which only validates the `web_search` tool turn): `null → none`; `selected_id ∉ id→url map → invalid verdict → one selection retry → else none` (the "Failure vs empty" invalid-verdict path); `selected_id ∈ map → website_url = map[selected_id]`, `website_origin = discovered`. Because the LLM only ever names an id, a hallucinated host is impossible by construction. Adaptations vs phase-2: **one** `selected_id` (not a list), **no** `metric_label`, **no** dedup/ceiling, and validation at the structured body rather than by the tool-call guard.
- **Store candidates for evaluation (revises "Where the result lives").** The id-indirection needs `candidates` + the `id → url` map only **in-memory for the turn**, so persistence is **not** required for correctness. To evaluate web-search quality after the run, the full candidate set is persisted to a dedicated **`state.discovery_search_results[(category_id, place_id)]`** — `{objective, search_queries, candidates: [{id, url, title, text}], selected_id, resolved_url, retrieved_at}` — kept **separate** from the clean verdict in `website_search_results`. This **revises** the earlier "only the resolved verdict is persisted; raw candidates are transient" rule.
- **Store gate decisions for evaluation (Stage 0 telemetry).** Mirroring "Store candidates for evaluation" (Stage 1), every Stage-0 decision is recorded so the gate's rule can be audited and tuned offline, kept **separate** from the clean verdict in `website_search_results`.
  - *Coverage: all work items.* The Stage-0 pre-pass writes one entry for **every** work item it evaluates — both `official` and `discovery` verdicts (unlike `discovery_search_results`, which exists only for the declined subset that searched).
  - *Location & key.* `state.official_gate_results[(category_id, place_id)]`, written during the synchronous Stage-0 pre-pass (see "Batch orchestration").
  - *Record shape.* `name` (raw `rec.name`), `website` (raw Google `websiteUri`), `host` (normalized netloc), `registered_domain` (`sld.suffix`), `sld`, `suffix`, `compact_name`, `compact_sld` (the two match operands), `verdict` (`official` / `discovery`), `reason_code` (`presence_empty` · `no_registrable_domain` · `denylist_hit` · `sld_match` · `sld_no_match`). **No `retrieved_at`** — the store is decision telemetry, not time-sensitive (a per-run timestamp, if needed, lives at the run level). Fields that don't apply to a given `reason_code` (e.g. `sld` / `compact_sld` when `presence_empty` or `no_registrable_domain`) are `None`.
  - *What it unlocks.* Aggregate the official/discovery rate and the `reason_code` distribution (decline dominated by `denylist_hit` or `sld_no_match`?) and which `registered_domain`s hit the denylist (denylist tuning). **False-DISCOVERY detection is automatic:** join `discovery` rows against `website_search_results` — when Stage 1 later resolved a URL whose registrable domain equals this row's `registered_domain`, the gate wrongly rejected the Google URL (a measurable false-negative). **False-OFFICIAL spot-check is cheap:** filter `verdict=official` and scan `name` ↔ `sld` / `website` (the decoy case still needs a human, but this store makes it a quick scan, not a re-run).
- **Always-produce rule.** The object is always created, one per work item. When the Google `websiteUri` **passes the official-URL gate (Stage 0)**, `website_url` + `website_origin=google` are **populated from Google** and **no search runs** (`website_url` + `website_origin` are the whole verdict; nothing raw-result-derived is persisted — raw candidates are transient, per "Where the result lives").
- **No dedup across categories.** One physical place appearing under two categories = two work items (same `place_id`, different `category_id`). Each work item runs **its own** discovery (duplication accepted; single-flight intentionally *not* used).
- **URL format.** The LLM no longer emits a URL — it returns a `selected_id`, and the app resolves it to a **verbatim** search-result URL from the candidate set (see "Candidate id-indirection"), so there is **no LLM-typed URL** to normalize or `HttpUrl`-validate; the resolved URL is exactly what the search returned for that hit. No crawl host-clamp is needed because the phase-2 `firecrawl_map` `url` is **app-injected** from this object (see R3.M1.1), so there is never an LLM-supplied host to compare.
- **Effect of `none`.** Phase 2 skipped for this amenity (no official URL to crawl); metrics rely on web evidence. Phase 1 still runs. When a URL **is** present, phase 1 **also** uses it for **`factual` metrics only** — folding the host into some of that metric's queries to scope them to the official site — but *in addition to* broader off-site queries, not as a replacement (web and scrape must stay complementary per D7; hard-scoping every query collapses web evidence onto the site). `experiential` metrics get **no** host-scoped query: the official site is the amenity's own marketing and cannot meet their verification bar (lived customer experience), and they are never scraped in phase 2.

**Batch orchestration — finalized: synchronous Stage-0 pre-pass, then `asyncio.gather` over the declined subset (Option A).**
Discovery runs **before the loop, behind a hard barrier**, but **Stage 0 (`official_url_gate`) runs in a synchronous pre-pass over all work items *before* the fan-out** — not inside the per-item coroutine. The fan-out is therefore **one coroutine per *gate-declined* work item**, not per work item.

- **Pre-pass (synchronous, all work items).** For each work item: `official` → write `website_search_results[key] = {website_url=rec.website, website_origin=google}` immediately (no task, no semaphore, no search); `discovery` → add the work item to the declined set. Wrap each gate call so a malformed record cannot crash the pre-pass — a gate error routes that item to the **declined set** (safe default → it runs Stage 1), **never silently to `none`**.
- **Fan-out (async, declined subset only).** Build one discovery coroutine per declined work item, each wrapped in `async with discovery_sem`; `await asyncio.gather(*tasks, return_exceptions=True)` is the barrier — the loop starts only after it returns. These coroutines start at **Stage 1** and do **not** re-check the gate. Each coroutine first checks `breaker_open` (R3.M1.5) and returns `none` without searching when it is open. Each task has a per-call timeout and swallows its own failure; any exception slot or timeout → a `none` result.
- **Reconvergence / RC8.** Pass-items are written before the fan-out and declined-items as their coroutines resolve, so when the barrier returns the dict holds an entry for **every** work item (`google` / `discovered` / `none`) — RC8 ("URL first, for everyone") holds. The barrier waits **only** on the declined subset, but dict completeness does not depend on its size.
- **Placement-only.** Per-item verdicts and `website_search_results` are identical to running the gate inline; the gate stays defined once under "Google-provided URL handling." This decision fixes only *where* Stage 0 is invoked.
- **Latency & efficiency.** Stage 0 is pure, synchronous, sub-millisecond (`urlsplit` + `tldextract` + set lookup) with **zero I/O**, and Google usually yields a usable site, so most items pass. Running the gate inside a coroutine would make every gate-passing item consume a `discovery_sem` slot and a scheduled task for a CPU-only no-op. Hoisting makes the **barrier's latency scale with the declined subset, not N**, removes semaphore churn and task-scheduling for no-op items, and lets the batch know `len(declined)` **up front** for Parallel rate planning. Because the loop has not started, discovery still gets the full Parallel rate budget with no phase-1 contention.

> **Resolved — instructed, not injected.** The full `address` is passed to the LLM verbatim and the instruction directs it to use **only the postal code** for locality scoping; the app parses nothing. *Remaining instruction detail:* the prompt must also cover the **degrade when no postal code is present** (rural / some international) — fall back `postal code → locality/city → name-only` so a missing postal code never blocks the search.

## R3.M1.4 — Run the Phase Loop and Triage per Amenity

**Goal.** For one amenity: run phase 1 (LLM + `web_search`: one search per metric, all in the first turn, then at most one retry turn covering only the metrics whose search `failed`); run the triage turn (`sufficient`/`unresolved` per metric); run phase 2 (LLM + Firecrawl `map` → select → `scrape`) only when ≥1 **phase-2-eligible** metric (unresolved **and** `factual`, i.e. carrying a `scrape_target`) exists AND a URL exists, until the LLM stops calling tools or the phase-2 budget is spent. Return the full conversation and the `metrics_source_content` store.

**Problem.** Nothing drives the assistant/tool-call/tool-result cycle today. Phase switching, loop termination, and the crawl decision need defined rules. The LLM's "settled" judgment must become a readable field. Tool failures must not stop the amenity or run. An LLM provider-chain failure needs one defined outcome per amenity, and a provider outage must not make every remaining amenity wait through the full chain timeout.

**Finalized approach — Split loops (phase-1 loop, phase-2 loop).**
Two dedicated loop functions with triage as an explicit step between them; each loop hardcodes its own tool and budget. The orchestrator runs `phase1_loop → triage → (conditionally) phase2_loop`. This keeps each phase's rules read in isolation and lets the two phases evolve independently, at the cost of some duplicated message-cycle boilerplate across the two loop bodies (acceptable, and a shared helper for the raw assistant↔tool-call↔tool-result cycle can absorb most of it without merging the phases).

**Triage capture mechanism (settled):** a **separate strict-schema no-tools request** between the two loops — the finalized triage decisions below (closed-enum structured response + retry-twice robustness) require it; free-text-JSON-in-message can't guarantee the closed schema, and a `report_triage` tool call would fight C3.1.2's tools-vs-`response_format` separation.

**Prerequisite — per-kind gateway retry limits (C3.1.1 change; the retry rules below depend on it).**
- **What is wrong today.** The gateway takes its retry limit from one shared value, `max_retries = len(RETRY_BACKOFFS_SECONDS)`, and applies it to every failure kind. That ties timeout/transport retries to rate-limit retries (the code even relies on "both sequences are the same length"), so shortening one shortens the other.
- **Change.** Give each failure kind its own backoff tuple and take the retry limit from the tuple of the kind that **failed** (`len(backoffs_for(kind))`), not from a shared constant. Then `RETRY_BACKOFFS_SECONDS = (2.0,)` (timeout/transport: one retry) and `RATE_LIMIT_BACKOFFS_SECONDS = (30.0, 30.0)` (rate limit: still two retries, second wait shortened from 60 s to 30 s — the two waits cumulatively span ~60 s from the first `429`, enough to clear a one-minute window; worst-case rate-limit waiting drops from 90 s to 60 s) can differ. Later tuning (for example a different count for Firecrawl) becomes a one-line config change.
- **Why.** Two retry layers stack on one phase-1 search: the **gateway** retries transient failures *inside* a single call, and the **loop's per-metric budget retry** re-runs the whole cycle (LLM re-emit → guard → gateway → shape) only after the gateway has given up. With the old two-retry rule a timing-out call held a metric for ~95 s (30 + 2 + 30 + 3 + 30) before the budget layer could react. One gateway retry cuts that to ~62 s (30 + 2 + 30); the budget retry covers whatever still fails.
- **Who retries what (one owner per failure kind).**

| Failure | Retried where | Why |
|---|---|---|
| Timeout | Gateway, **one** retry after a 2 s wait; then the budget layer | A single slow response is often one-off, so one cheap retry avoids an LLM turn. A second gateway retry would stack another 30 s wait. If the retry also times out the call returns `failed` and the metric's budget retry takes over. |
| Dropped connection / transport error | Gateway, **one** quick retry (2 s) | Cheap and usually works; saves an LLM turn. |
| Rate limit (429) | Gateway wait (30 s, then 30 s); a response `Retry-After` overrides | Only waiting fixes it; an immediate budget retry would hit the same 429 and burn the metric's one retry. |
| Guard rejection | Budget layer only | Rejected before any network call — the gateway never sees it. |

- **Scope.** The gateway function is shared by every gateway call (discovery search, Firecrawl `map`/`scrape`, phase 1, phase 2), so all of them get the one-retry timeout/transport rule; each keeps its own budget retry on top (R3.M1.3, phase 2).
- **Tests to update.** The gateway tests that assert the old waits (e.g. transport backoff `[2.0, 3.0]` in `test_c3_1_1_mcp_tool_gateway.py`) change to `[2.0]`; the rate-limit test changes its asserted waits from `[30.0, 60.0]` to `[30.0, 30.0]` (still one attempt plus two retries).

**Decisions — generally mandatory**
- **Two retry layers.** Gateway-internal retries (per the prerequisite above) are **not** counted against a metric's budget; the budget retry applies only after the gateway has returned a typed `failed`, and also covers guard rejections the gateway never sees.
- **Termination.** The loop enforces the attempt budget; the app, not the LLM, tracks attempts. Phase 1 ends by its turn rule below (both its turns use `tool_choice="required"`, so a reply with no `tool_calls` cannot occur); phase 2 ends when the assistant returns no `tool_calls`, or when its budget is spent. Before a call reaches the gateway, the loop checks this metric/amenity still has an attempt; a call with none left isn't executed. Phase 1 budget is spent for a metric when its search **terminates cleanly — `ok` *or* `empty` (R3.M1.2)** — or its one retry is used. **Phase 1 has at most two search turns:** turn 1 searches every metric; after it, if no metric is retry-eligible (its call `failed` or was guard-rejected, and its retry is unused), phase 1 ends **without another LLM call**; otherwise the loop runs one retry turn, after which every retried metric's budget is spent and phase 1 ends. A metric whose search returned `ok` or `empty` is never searched again, even though attempts remain on other metrics. Phase 2 follows the multi-step phase-2 budget in the Phase 2 scope below (`map` + **one `scrape` per phase-2-eligible metric**, deduped by URL to a **hard ceiling of 8 distinct scrapes per amenity**, each scrape with one retry). **Only a `failed` outcome, a timeout, or a guard rejection is retry-eligible; an `empty` result is terminal and is never retried (R3.M1.2).**
- **Concurrency.** Tool calls in one turn run together with `gather` under the per-server gateway semaphores (Parallel for search, Firecrawl for crawl). Calls are **async-native on the event loop, no thread offload** (C3.1.1). Results appended in `tool_call_id` order.
- **Failure handling (D5).** Two failure types, handled in opposite ways:
  - **Tool-call failure (continue).** Every tool call is shaped by **R3.M1.2** into exactly one `ok`/`empty`/`failed` `tool` message; the loop appends it and continues. Only `failed` is retry-eligible; `empty` is terminal.
  - **LLM provider-chain failure (stop and pass up).** When `call_turn` or `call_structured` raises `MetricResolutionProviderError` in phase 1, triage or phase 2, the step stops at once and passes the error up. No `tool` message is appended, no budget retry is used, and triage's invalid-body retry does not apply. The error carries `stage` and `cause` (`availability` / `content` / `circuit_open`, defined in C3.1.2 "Typed error").
  - **Amenity-level outcome.** A `MetricResolutionProviderError` from any LLM step of an amenity pipeline (phase 1, triage, phase 2, resolution R3.M2.2) ends that amenity. Its remaining steps are skipped, any evidence gathered is discarded, and every metric is `unresolved` with reason `resolution_call_failed`. `stage` records the failed step and `cause` records why; both go to the error and the pipeline's log line, not to the record (the record schema does not change). The run continues with the other amenities. Owned by the pipeline's catch in R3.M1.5.
  - **Discovery is not ended by this rule.** A discovery failure (R3.M1.3) keeps its own outcome: a `none` result, and the amenity still runs.
  - **Run-level circuit breaker and run-level raise.** Every LLM call in these steps first checks the run's circuit breaker; when it is open, the call is not made and the step raises `MetricResolutionProviderError(stage = <step>, cause = circuit_open)`, which the amenity-level outcome handles. Counter, trip rule, check point and run-level raise are defined once in R3.M1.5 "Provider-failure circuit breaker."
- **Conversation state.** One message list per amenity, provider-neutral format (C3.1.2). The split loops are **not** separate conversations: `phase1_loop`, the triage request, and `phase2_loop` all read and append to this **single shared message list** — "split" refers to the two loop *functions*, not the conversation.

**Decisions — problem-specific**
- **Phase 1 instruction content.** Amenity identity, the resolved `website_url` from the `website_search_results` object (R3.M1.3) when present, and every metric with `label`, `question`, `value_type`, `unit`, `enum_values`, `evidence_class`, `verification`, and `resolution_source.web_target` (the search direction — used for **both** classes; `scrape_target` / `review_target` are not shown in phase 1). Told to **emit one `web_search` per metric, for all metrics, in the first turn** (never split across turns) and tag each call with `metric_label`; and, **on a retry turn, to re-emit a call only for the metrics whose `tool` result `failed`**. **When a `website_url` is present AND the call's `metric_label` is a `factual` metric**, instruct the LLM to include at least one host-scoped query **alongside** broader off-site queries *within the same `web_search` call's `search_queries`* — never scoping every query to the host (web and scrape stay complementary per D7, per R3.M1.3). **For an `experiential` metric, no host-scoped query is used** (the instruction states this per metric, keyed off `evidence_class`, not as one global rule for the whole call).
- **Phase-1 retry turn (who retries).** The **LLM re-emits** the retry; the app never reissues a search call itself. The retry turn sees the full shared history (instruction, its own turn-1 calls with their `metric_label` / `objective` / `search_queries`, and every `tool` result), so nothing is re-sent and the turn-1 results stay in place; the LLM matches each `failed` result to its own call by `tool_call_id` and may reword the queries. The `failed` `tool` message states that the call failed, the failure kind in a few words (e.g. timed out), and the `metric_label` (the loop adds the label from the admitted call, since it is stripped before MCP execution); it carries **no retry flag** — the app owns the attempt count. **Both phase-1 turns call `call_turn` with `tool_choice="required"`** (matching discovery, R3.M1.3): the retry turn only runs when a metric `failed`, so there is always a call to make, and `"required"` rules out a reply with no `tool_calls` at the API level — no "no `tool_calls`" branch is specified.
- **Phase-1 web evidence recording.** After each turn, every `ok` `web_search` result is recorded **hit by hit**: each hit (`SearchExcerpt`: `url`, `title`, `text`) becomes one evidence item with `source_kind = web`, `url` = the hit's `url`, **`shaped_text` = the hit's `title` + `"\n"` + its `text`** (the excerpts joined with newlines), `retrieved_at` = the call's `retrieved_at`, and `metric_labels` = {the call's tagged metric}. `shaped_text` is exactly the title and excerpts the hit carries in the `tool` message (R3.M1.2 passes the result through unchanged), so R3.M2.4's quote check runs on what the LLM saw. Two hits in one call with the same `(web, url, shaped_text)` are one item (identity rule). An `empty` result has no hits and a `failed` call has no result, so neither records an item.
- **Coverage.** A metric no phase-1 call was tagged with is set `unresolved` by the app, whatever triage says.
- **Triage schema & output integrity.** Static, strict, closed **structured response**: `metric_label` + `status`, where `status` is a closed enum of exactly `sufficient` / `unresolved`. The schema is what guarantees label/status integrity. Labels are checked against the metric set; a body that omits a submitted label fails the label-set check and is handled by the robustness rule below.
- **Triage call robustness.** A schema mismatch / invalid body is rejected and **retried up to twice**. If it still fails, **every metric is treated as `unresolved`** (safe default) and the amenity continues (phase 2 then runs for every `factual` metric when a URL exists). This covers an invalid body only; a `MetricResolutionProviderError` from the triage call is not retried here and ends the amenity (Failure handling above).
- **Triage rule & judgment quality.** A metric is `sufficient` only if evidence meets its `verification` rule. Triage is an opinion; R3.M2 still gates each value. Judgment quality is ensured by **detailed instruction**: the triage prompt carries **one-shot examples and explicit edge cases** so the LLM makes the `sufficient` / `unresolved` call consistently.
- **Evidence-state → `unresolved`.** A metric whose phase-1 searches were all `empty` (genuine no-evidence) **or** all `failed` is `unresolved` — both map to `unresolved`. (The `empty` vs `failed` distinction is preserved by R3.M1.2 for R3.M2, not by triage.)
- **Phase-2 eligibility (derived from `evidence_class`).** Read off the class, never parsed from text: a metric enters phase 2 only if it is **`unresolved` after triage AND `factual`** (it carries a `scrape_target`). An unresolved **`experiential`** metric has no page to scrape — it skips phase 2 and goes to R3.M2 with its web evidence, where the amenity's Google-reviews block (read via its `review_target` hint) is the fallback source (R3.M2.1). Triage still judges every metric; eligibility only filters which unresolved metrics phase 2 acts on.
- **Incomplete evidence (spent budget).** When phase 1 ends with a metric still `failed` after its retry (or with its retry not taken), triage runs normally on the evidence that exists; any metric that obtained no value is `unresolved`. This applies to tool-call failures only; an LLM provider-chain failure ends the amenity and discards its evidence (Failure handling above).
- **`metrics_source_content` shape (finalized — normalized evidence set).** The store is **scoped to the amenity pipeline** (no `(category_id, place_id)` key — identity is ambient and carried on the returned `SpecificMetricsRecord`) and is a **normalized evidence set** — a flat list of items, each one distinct finding: `{ evidence_id, source_kind ∈ web|scrape|google_reviews, url (str|null), shaped_text, retrieved_at, metric_labels : set }`. **`evidence_id` is a UUID** the app generates when an item is first recorded; a later finding that merges into the item (same triple) keeps that id and only adds to `metric_labels`. **Item identity is the triple `(source_kind, url, shaped_text)`**: two findings with an identical triple are stored **once**, their `metric_labels` unioned; findings that share a `url` but differ in `shaped_text` stay **distinct items**. So objective-scoped web excerpts from the same URL never collapse (different query → different `shaped_text` → distinct item, single metric), while a scraped page serving several metrics is stored **once** carrying all their labels in `metric_labels` (fetch-once / fan-out). **Google reviews** are one amenity-level item (`source_kind = google_reviews`, empty `metric_labels`), passed to every metric at resolution. **Why this shape — two requirements:** (1) *downstream (R3.M2.2)* reads per metric — each metric's bucket is the items whose `metric_labels` contains that label, so every metric sees its own evidence while identical text is held only once; (2) *storage (log + database)* — the set maps **one-to-one to persistence with no reshape**: `evidence(evidence_id PK, source_kind, url NULL, shaped_text, retrieved_at)` (one row per item) + `evidence_metric(evidence_id FK, metric_label)` (one row per metric an item serves; a `google_reviews` row has no join row); `url` is non-unique and never a key. Consequence for R3.M2.4: a metric's quote is provenance-checked against **that metric's** items (same-URL excerpts route to the right metric via `metric_labels`), and `support`/`as_of` come from the cited items.
- **Phase 2 scope (finalized — `map` → select → `scrape`).** A uniform tool-calling loop (D1 preserved), not a single crawl. The instruction names the **phase-2-eligible** metrics (unresolved + `factual`) and their `resolution_source.scrape_target` hints.
  - **Tools:** `firecrawl_map` + `firecrawl_scrape` — the gateway operations, result parsers, capability check, and shape probe all live in **C3.1.1** (crawl retained there, unused by M3); this section only drives the loop over them. The LLM's **first Phase-2 tool call is `firecrawl_map`** (app-injected `url` = the resolved official homepage from `website_search_results`); map returns the site's link set, no page content. The app shapes it into an **id + URL candidate list** (opaque ids, issued fresh per map result, selection-only) returned as the `tool` message.
  - **Selection via id-indirection (per-metric):** the LLM emits `firecrawl_scrape` tool calls **one page per phase-2-eligible metric** — each call carries an `id` (**never a URL**) plus a **required `metric_label` (≥1; a list is allowed** when one page serves several metrics). The guard (R3.M1.1) validates each id against the issued set (unknown / out-of-range → guard failure, not executed), **requires at least one `metric_label`** (an untagged scrape is rejected — no orphan) and checks every label against the **phase-2-eligible set** supplied in `validation_ctx` (an experiential or already-sufficient label → guard failure), **dedups by resolved URL across all requests**, enforces the **hard ceiling of 8 distinct scrapes per amenity** (surplus dropped → those metrics stay on web evidence), then **substitutes the real URL verbatim** before the call reaches the gateway. URL stays app-controlled; URL text never passes through the model. Scrapes run concurrently under the Firecrawl semaphore via `gather`.
  - **Budget (multi-step):** `map` (1 call; `failed`/timeout → one retry, then give up Phase 2 → metrics stay on web evidence) → **selection turn** (invalid → one retry; still invalid → empty selection → no scrape, web-only) → **the deduped scrape set** — one page per phase-2-eligible metric, collapsed to **≤ 8 distinct URLs** (each scrape: `failed`/timeout → one retry, still `failed` → skip that page, don't fail the amenity; **`empty` → normal continuation** — the empty `tool` message is appended and the loop carries on, not retried, not a skip; R3.M1.2). A scrape's `failed`/`empty`/retry is decided **per fetch**, shared across every metric that requested that URL.
  - **Dedup + fan-out cycle (finalized — build exactly this way):**
    1. **Collect** — from the selection turn, gather every `(metric_label, id)` request (one page per phase-2-eligible metric; a request may list several metrics).
    2. **Resolve** — map each `id` to its real URL via the candidate list.
    3. **Dedup by URL** — group requests by resolved URL → **one `firecrawl_scrape` per unique URL**, carrying the **union** of the metrics that asked for it (a URL requested for three metrics is scraped **once**, not three times).
    4. **Ceiling** — if the unique-URL set exceeds **8**, drop the surplus (those metrics stay on web evidence).
    5. **Fetch once** — run the ≤ 8 scrapes concurrently (Firecrawl semaphore); each URL's `ok`/`empty`/`failed` + its one retry is decided **once**.
    6. **Record after results** — store the single shaped result as **one evidence item** (`source_kind = scrape`) carrying the **union of the requesting metrics** in `metric_labels` (stored once — no per-metric duplication); a `failed`/`empty` fetch records no item (each requesting metric simply gets no item from that URL).
    This is the one place the many-to-many (page ↔ metrics) is resolved: **fetch is per-URL, attribution is per-metric.**
  - **Best-effort (accepted constraint).** "One scrape per phase-2-eligible metric" guarantees an *attempt*, not evidence. A metric can still end `no_evidence` when `map` surfaced no plausible page, the URL-only page guess was wrong (`map` returns no content preview), or the scraped page simply lacks the answer. Accepted (D5).
  - A successful Phase 2 isn't repeated. **No second triage.**
  - **Candidate-list bounding before selection (finalized).** The `map` result is trimmed to **at most 50 candidate `(id, url)` pairs** before it is shown to the LLM for selection. If `map` returns more, the app caps the list at 50 (a path pre-filter / `map search` may inform *which* 50, but the ceiling is 50).
- **Skip cases.** Phase 2 skipped when **no metric is phase-2-eligible** (every metric is `sufficient`, or every unresolved metric is `experiential`), or `website_search_results.website_url` is `None` (R3.M1.3).

### Steps of sub-component

The sections above describe R3.M1.4 as one block. The three steps below split that same content by step (`phase1_loop → triage → (conditionally) phase2_loop`) so each can be read, built and tested in isolation. They restate decisions already finalized above; where a step needs a cross-cutting rule (the per-kind gateway retry prerequisite, the `metrics_source_content` shape), it points back to that text instead of redefining it.

#### 1. Phase-1 Loop

##### Goal
For one amenity, search **every** metric (factual and experiential alike) with one `web_search` per metric, all in the first turn, then run at most **one retry turn** covering only the metrics whose search `failed`. Each turn appends its `tool` messages to the amenity's single shared conversation and records web evidence items into `metrics_source_content`.

##### Problem it aims to solve
Nothing drives the assistant → tool-call → tool-result cycle. Phase 1 needs defined rules for termination, per-metric budgets and retries, attributing each search to the metric it serves, mixing on-site and off-site queries without collapsing web evidence onto the official site, keeping a tool failure from stopping the amenity or the run, and defining what happens when the LLM provider chain itself fails.

##### Finalized approach
A dedicated `phase1_loop` function that runs the shared R3.M1 tool-turn cycle (catalog → `call_turn` → guard → gateway → shape) with `context = metric_web_search`, `web_search` as its only tool and `tool_choice="required"`, **at most twice**: turn 1 for all metrics, and one retry turn only if some metric is retry-eligible. It hardcodes its own budget (**1 search + 1 retry per metric**). Every call is tagged with a `metric_label`. **The LLM produces every call, including retries; the app owns attempts** — it decides whether a retry turn happens and which metrics may be retried. The guard (R3.M1.1) only admits or rejects. A shared helper for the raw assistant ↔ tool-call ↔ tool-result cycle absorbs the boilerplate it shares with phase 2.

##### Prerequisite — provider failure class on `LLMProviderError` (C3.1.2 change, NOT DONE; the `cause` rule and the breaker depend on it)
- **What is wrong today.** `LLMProviderError` carries only a message. `call_turn` (`llm_provider.py`, provider loop) logs each provider's failure and moves to the next provider, keeping nothing about the kind of failure. When the chain runs out, the raised `MetricResolutionProviderError` carries `stage` only, so phase 1 cannot tell an outage (timeout, 5xx) from a content failure (refusal) and cannot set `cause`.
- **Change.** At each place a provider raises `LLMProviderError`, set a `failure_class` on it, because that code already knows what went wrong:
  - `availability`: timeout, 5xx, connection error, or a 429 after its retries ran out.
  - `content`: a refusal, an abnormal `finish_reason`, or the defensive-parse anomaly.
  `call_turn` and `call_structured` collect one `failure_class` per failed provider. When the chain is exhausted they raise `MetricResolutionProviderError` with `cause = availability` if **every** collected class is `availability`, and `cause = content` if **any** is `content` (the Error cause rule below). `circuit_open` is never set by a provider; only the caller-side breaker check raises it.
- **Why.** The run-level breaker (R3.M1.5) counts only `cause = availability`. Without `failure_class`, no failure can be labelled `availability`, the counter never moves, and the breaker can never trip during an outage.
- **Scope.** `call_turn` and `call_structured` are shared by discovery (R3.M1.3), phase 1, triage, phase 2 and resolution (R3.M2.2), so all of them get `cause`. `cause` is set only when `provider_error_cls` is `MetricResolutionProviderError`; R1's error class and behavior are unchanged.
- **Tests to add.** Fake providers failing with: all timeouts / 5xx → `availability`; one refusal plus one timeout → `content`; all refusals → `content`. Existing R1 provider-chain tests pass unchanged.

##### Traceflow
```text
phase1_loop(amenity)
  instruction: amenity identity + website_url (if any) + every metric
               (label, question, value_type, unit, enum_values, evidence_class,
                verification, resolution_source.web_target)
  rules: turn 1 → ONE web_search per metric, ALL metrics in this turn, each tagged with metric_label
         retry turn → re-emit ONLY for metrics whose tool result failed
         both turns → tool_choice="required" (every reply carries ≥1 tool call)

  TURN 1 (all metrics)
    [atom, context = metric_web_search]
      ① catalog (web_search; + metric_label)
      BREAKER CHECK before call_turn: breaker_open → raise ProviderError(stage=phase1, cause=circuit_open)
      ② call_turn (required)
         raises MetricResolutionProviderError → phase 1 STOPS, passes it up
           (no tool message appended · no budget retry used · amenity ends in R3.M1.5)
      ③ guard (metric_label ∈ metric set)
      LOOP budget check BEFORE execute: metric with no attempt left → not executed
      ④ gateway web_search × calls (gather, Parallel sem)   ⑤ shape ok / empty / failed
    append tool messages (tool_call_id order)
      failed tool message = "failed" + kind (e.g. timed out) + metric_label   (no retry flag)
    record web evidence items (ok results only), one per hit:
      source_kind = web · url = hit url · shaped_text = title + "\n" + excerpts
      retrieved_at = call's · metric_labels = {tagged metric} · evidence_id = new UUID

  APP CHECK: any metric retry-eligible?  (call failed or guard-rejected, retry unused)
    NO  → phase 1 ends, NO further LLM call → triage
    YES → RETRY TURN (same atom, same shared history; nothing re-sent)
            same BREAKER CHECK + same provider-failure rule as turn 1 (stop, pass up)
            LLM matches failed results by tool_call_id, re-emits ONLY those metrics (may reword)
          each retried metric's result is final (ok / empty / failed) → phase 1 ends → triage

  ok / empty metric = done, never re-searched · empty = TERMINAL (burns budget)
  (gateway's own 1-retry for timeout/transport does NOT use this budget)

  provider failure passed up → R3.M1.5 pipeline catch: amenity ends, evidence discarded,
    every metric unresolved(resolution_call_failed); cause = availability → breaker counter +1
```

##### Decisions — Generally mandatory
- **Termination.** Phase 1 has **at most two search turns**. After turn 1, if no metric is retry-eligible, the phase ends **without another LLM call**; otherwise one retry turn runs, and the phase then ends because every retried metric's budget is spent. Before a call reaches the gateway, the loop checks the metric still has an attempt; a call with none left is not executed. A metric's budget is spent when its search **terminates cleanly — `ok` *or* `empty` (R3.M1.2)** — or its one retry is used. Only a `failed` outcome, a timeout, or a guard rejection is retry-eligible; `empty` is terminal and never retried. An `ok` or `empty` metric is never searched again.
- **Two retry layers.** Gateway-internal retries (the **per-kind gateway retry limits** prerequisite above) do not count against the metric's budget; the budget retry applies only after the gateway has returned a typed `failed`, and also covers guard rejections the gateway never sees.
- **Concurrency.** Tool calls in one turn run together with `gather` under the Parallel gateway semaphore, async-native on the event loop (C3.1.1); results are appended in `tool_call_id` order.
- **Failure handling (D5).**
  - **Tool-call failure (phase 1).** Every call is shaped by R3.M1.2 into exactly one `ok` / `empty` / `failed` `tool` message; the loop appends it and continues.
  - **LLM provider-chain failure (phase 1).** If `call_turn` raises `MetricResolutionProviderError` (turn 1 or the retry turn), phase 1 stops and passes it up. No `tool` message is appended and no budget retry is used.
  - **Error cause (C3.1.2).** `MetricResolutionProviderError` carries `stage` and a required `cause`:
    - `availability`: **every** provider in the chain failed with a timeout, 5xx, connection error, or a 429 after its retries ran out.
    - `content`: at least one provider failed with a refusal, an abnormal `finish_reason`, or the defensive-parse anomaly. A chain with mixed causes is `content`.
    - `circuit_open`: the breaker was open, so no call was made.
  - **Amenity-level outcome.** A `MetricResolutionProviderError` from any LLM step of an amenity pipeline (phase 1, triage, phase 2, resolution) ends that amenity. Its remaining steps are skipped, any evidence gathered is discarded, and every metric is `unresolved` with reason `resolution_call_failed`. `stage` records the failed step and `cause` records why (on the error and in the pipeline's log line; the record carries only the reason). The run continues with the other amenities.
  - **Discovery is not ended by this rule.** A discovery failure (R3.M1.3) keeps its own outcome: `none` result, and the amenity still runs.
  - **Run-level circuit breaker** (owned by R3.M1.5).
    - *Counter.* One shared counter per run. It goes up by 1 for each `cause = availability` failure from an amenity pipeline **or** a discovery LLM call (tool turn or selection turn), and resets to 0 when any LLM call succeeds. Safe without a lock because everything runs on one event loop (C3.1.1).
    - *Trip.* The breaker opens when the counter reaches `N` (configurable, default 3) and stays open for the rest of the run.
    - *Check point.* `breaker_open` is checked immediately before every `call_turn` and structured call (phase 1, triage, phase 2, resolution), after the LLM-call permit is acquired, and before each discovery coroutine starts Stage 1.
    - *When open (amenity step).* The call isn't made. The step raises `MetricResolutionProviderError(stage = <step>, cause = circuit_open)`, which the amenity-level outcome handles. Phase 1 starts with `call_turn`, so an amenity that hasn't started yet stops at its first check, before any search or Firecrawl call.
    - *When open (discovery).* The work item skips its search and selection turn and gets a `none` result.
    - *Labelling.* Breaker-skipped amenities use reason `resolution_call_failed` with `cause = circuit_open`. No new unresolved reason is added, so the record schema doesn't change.
    - *Not counted.* `content` and `circuit_open` failures never move the counter.
  - **Run-level raise.** The run raises `MetricResolutionProviderError` when no amenity pipeline completed its LLM steps without a provider error (every amenity failed, was breaker-skipped, or a mix). Otherwise it returns records, with the failed and skipped amenities unresolved.
- **Conversation state.** One message list per amenity, provider-neutral (C3.1.2), shared with triage and phase 2 — the loops are separate functions, not separate conversations.

##### Decisions — Problem-specific nuances
- **Instruction content.** Amenity identity, the resolved `website_url` (R3.M1.3) when present, and every metric with its fields and `resolution_source.web_target` — the search direction used for **both** classes. `scrape_target` / `review_target` are **not** shown in phase 1. The LLM is told to **emit one `web_search` per metric, for all metrics, in the first turn** (never split across turns), tag each call with `metric_label`, and **on a retry turn re-emit a call only for the metrics whose `tool` result `failed`**.
- **Retry turn — who retries and what the LLM sees.** The **LLM re-emits** the retry; the app never reissues a search call itself. The retry turn replays the full shared history (instruction, the LLM's own turn-1 calls with their `metric_label` / `objective` / `search_queries`, and every `tool` result), so nothing is re-sent and the turn-1 results stay in place. The LLM matches each `failed` result to its own call by `tool_call_id` and may reword the queries.
- **`failed` tool message content.** States that the call failed, the failure kind in a few words (e.g. timed out), and the `metric_label` — the loop adds the label from the admitted call, since it is stripped before MCP execution. It carries **no retry flag**: the app owns the attempt count, and the instruction states the one-retry rule once.
- **`tool_choice = "required"` on both turns.** Turn 1 and the retry turn both call `call_turn` with `tool_choice="required"`, matching discovery (R3.M1.3). The retry turn only runs when at least one metric `failed`, so there is always a call to make; the instruction says which metrics to re-emit; and `"required"` rules out a reply with no `tool_calls` at the API level. A "no `tool_calls`" case is therefore not handled — it cannot occur. (`"required"` forces at least one call, not one per metric; one call per metric is the instruction's job, and an untagged metric is caught by the coverage rule.)
- **Host-scoped queries are per metric, keyed off `evidence_class`.** When a `website_url` is present **and** the call's `metric_label` is a `factual` metric, the instruction asks for at least one host-scoped query **alongside** broader off-site queries inside the same call's `search_queries` — never scoping every query to the host (web and scrape stay complementary per D7). For an `experiential` metric, **no** host-scoped query is used: the official site is the amenity's own marketing and cannot meet an experiential `verification` bar, and experiential metrics are never scraped.
- **Evidence recording.** Each hit of an `ok` `web_search` result becomes one evidence item:
  - `source_kind = web`, `url` = the hit's `url`, `retrieved_at` = the call's `retrieved_at`, `metric_labels` = {the call's tagged metric}, `evidence_id` = a new UUID.
  - **`shaped_text` = the hit's `title` + `"\n"` + its excerpts** (joined with newlines) — exactly what the hit carries in the `tool` message, so R3.M2.4's quote check runs on what the LLM saw.
  - Two hits in one call with the same `(web, url, shaped_text)` are one item; the same URL with different `shaped_text` is a **distinct item**, never collapsed (see the `metrics_source_content` shape bullet above).
  - An `empty` result has no hits and a `failed` call has no result, so neither records an item.
- **Coverage.** A metric no phase-1 call was tagged with is set `unresolved` by the app, whatever triage says.
- **Incomplete evidence (spent budget).** If the phase ends with a metric still `failed` after its retry (or with its retry not taken), triage runs normally on the evidence that exists. This covers tool-call failures only; an LLM provider-chain failure in either turn ends the amenity and discards the turn-1 evidence (Failure handling above).
- **Not yet decided (flagged for discussion).** The guard works on the whole message, all-or-nothing, so one malformed call (for example a `metric_label` not in the set) rejects the entire turn and every metric in it loses an attempt, whereas execution failures are per call. *(Resolved: who triggers the retry — the LLM re-emits, for failed metrics only; fan-out across metrics — all metrics in turn 1, by instruction; `tool_choice` — `"required"` on both turns.)*

##### Iteration 1 — retry-turn `content` refusal keeps the amenity (DECIDED, NOT IMPLEMENTED)

**What changes.** A `MetricResolutionProviderError` with `cause = content` raised by the **retry turn** no longer ends the amenity. Only the metrics that turn was retrying are marked `failed` (failure kind `retry_refused`); the turn-1 evidence is kept, and the amenity continues to triage on the evidence that exists.

**What stays the same.**
- Any provider failure on **turn 1** still ends the amenity (no evidence exists yet, so nothing is lost).
- A retry-turn failure with `cause = availability` or `cause = circuit_open` still ends the amenity: an outage or an open breaker means the next LLM call for this amenity (triage) will almost certainly fail too.
- Tool-call failures are unchanged (shaped `failed`, the loop continues).

**Why.**
- The retry turn only serves the metrics whose turn-1 search failed. Metrics that ended `ok` or `empty` on turn 1 do not depend on it, so discarding their evidence over this call throws away paid, successful searches.
- `content` means this particular request was refused, not that the provider is down (C3.1.2 "Typed error"). Triage is a different request and may succeed.
- The spec already treats "retry not taken" as incomplete evidence that triage handles (Incomplete evidence bullet above); a refused retry turn is the same situation.
- Accepted risk: if the refusal was triggered by something in the gathered evidence, triage reads that evidence and may be refused too. Then the amenity ends at triage under the normal amenity-level outcome, so the cost is at most one extra LLM call.

**Rule (replaces the provider-failure rule for this one case).**
- Retry turn raises `MetricResolutionProviderError` with `cause = content` → phase 1 catches it instead of passing it up.
- Every metric that was retry-eligible for that turn (status `failed`, one attempt used) ends `failed` with `failure_kind = retry_refused`, and `attempts_used = 2` (the retry was spent).
- Nothing is appended to the conversation for the refused turn. The history ends on the turn-1 tool messages, which is still replayable (every turn-1 call was answered).
- Turn-1 evidence in `metrics_source_content` is kept; `turns_run = 2`.
- Phase 1 returns a normal `Phase1Result`; the pipeline record is `completed`. R3.M2 later maps `retry_refused` to the same tool-failure reason as any other `failed` metric.
- Breaker: unchanged. `content` never moves the counter; `_counted_llm_call` still records the failure (a no-op for `content`).
- Logging: one WARN `r3m1_4.retry_turn_refused` (a degrade that raises nothing) with `stage`, `cause`, and the affected labels.

**Superseded text.** For a retry-turn `content` failure only, this iteration overrides: the traceflow line "same BREAKER CHECK + same provider-failure rule as turn 1 (stop, pass up)", the Failure handling bullet "LLM provider-chain failure (phase 1)", and the last sentence of the Incomplete evidence bullet ("an LLM provider-chain failure in either turn ends the amenity and discards the turn-1 evidence").

**Implementation impact (to do).**
- `_phase1_loop` (`specific_metric_resolution.py`): wrap the retry-turn call; on `cause == "content"` apply the rule above; re-raise any other cause.
- Tests: flip `test_retry_turn_provider_failure_discards_only_that_amenitys_evidence` (behavior suite) to expect A `completed` with turn-1 evidence and `weekday_crowding` `failed`/`retry_refused`; add a case asserting an `availability` failure on the retry turn still ends the amenity; update the retry-turn case of `test_provider_error_in_either_turn_propagates_with_cause` (`test_r3_m1_4_phase1_loop.py`) to the new split by cause.
- `R3_M1_4_Phase1_Loop_Implementation_Plan.md`: note the iteration under the `_phase1_loop` method detail and drift entry.

#### 2. Triage

##### Goal
After phase 1, produce one `sufficient` / `unresolved` judgment per metric from the evidence collected, for **both** classes. The result is what decides which metrics may go on to phase 2.

##### Problem it aims to solve
The LLM's "settled" judgment must become a readable field with guaranteed integrity (every submitted label answered, status from a closed set). Free-text JSON in a message cannot guarantee that, and a `report_triage` tool call would fight C3.1.2's separation of tools from `response_format`.

##### Finalized approach
A **separate strict-schema, no-tools structured request** (C3.1.2 `call_structured`) between the two loops, run over the same shared message list. The schema is static, strict and closed: `metric_label` + `status ∈ {sufficient, unresolved}`.

##### Traceflow
```text
triage(amenity)                      [C3.1.2 call_structured · strict schema · NO tools]
  BREAKER CHECK before the call: breaker_open → raise ProviderError(stage=triage, cause=circuit_open)
  MetricResolutionProviderError → triage STOPS, passes it up (not retried; amenity ends in R3.M1.5)
  returns { metric_label, status ∈ sufficient | unresolved }  per metric (both classes)
  label-set check (labels ∈ metric set; no submitted label omitted)
  schema mismatch / invalid body → retry up to 2× → still bad → ALL metrics unresolved
  app overrides (ignore LLM):
    metric no phase-1 call was tagged with           → unresolved   (coverage)
    all phase-1 evidence empty OR all failed          → unresolved
  → derive phase-2 eligibility:  unresolved AND factual
```

##### Decisions — Generally mandatory
- **Conversation state.** Triage reads and appends to the amenity's single shared message list; it is a request on the same conversation, not a new one.
- **Failure handling (D5).** An invalid triage body never stops the amenity: after the retries below, every metric is treated as `unresolved` (safe default) and the pipeline continues. A `MetricResolutionProviderError` from the triage call (including `cause = circuit_open` from the breaker check) is different: triage stops and passes it up, and the amenity ends per the R3.M1.4 Failure handling amenity-level outcome.
- **Judgment is an opinion, not a gate.** Triage never commits a value; R3.M2 still gates each value.

##### Decisions — Problem-specific nuances
- **Schema & output integrity.** Static, strict, closed structured response; the schema guarantees label/status integrity. Labels are checked against the metric set, and a body that omits a submitted label fails the label-set check and goes to the robustness rule.
- **Call robustness.** A schema mismatch / invalid body is rejected and **retried up to twice**. If it still fails, **every metric is `unresolved`** and the amenity continues (phase 2 then runs for every `factual` metric when a URL exists). A provider-chain failure is not retried here (see Failure handling).
- **Rule & judgment quality.** A metric is `sufficient` only if the evidence meets its `verification` rule. Quality comes from **detailed instruction**: the prompt carries one-shot examples and explicit edge cases so the call is consistent.
- **Evidence-state → `unresolved`.** A metric whose phase-1 searches were all `empty` (genuine no-evidence) **or** all `failed` is `unresolved`. The `empty` vs `failed` distinction is preserved by R3.M1.2 for R3.M2, not by triage.
- **Coverage.** The app, not the LLM, sets any untagged metric `unresolved`.
- **Phase-2 eligibility (derived from `evidence_class`).** Read off the class, never parsed from text: a metric is eligible only if it is `unresolved` after triage **and** `factual` (it carries a `scrape_target`). An unresolved `experiential` metric skips phase 2 and goes to R3.M2 with its web evidence, where the Google-reviews block (read via `review_target`) is the fallback (R3.M2.1). Triage still judges every metric; eligibility only filters what phase 2 acts on.
- **Incomplete evidence.** When phase 1 ended with a metric still `failed` after its retry (or with its retry not taken), triage runs normally on the evidence that exists; any metric that obtained no value is `unresolved`.

#### 3. Phase-2 Loop

##### Goal
For the **phase-2-eligible** metrics only (`unresolved` after triage **and** `factual`), run `firecrawl_map` → select → `firecrawl_scrape` on the amenity's official site, record scrape evidence into `metrics_source_content`, and hand the amenity on to R3.M2.

##### Problem it aims to solve
Official-site evidence needs a loop that never lets the LLM supply a URL, resolves the many-to-many between pages and metrics (one page can serve several metrics; each metric wants one page), bounds the fan-out, and survives `map` / `scrape` failures without failing the amenity.

##### Finalized approach
A dedicated `phase2_loop`: a **uniform tool-calling loop (D1 preserved), not a single crawl**. It runs only when ≥1 metric is phase-2-eligible **and** a `website_url` exists. Step order is `map` (app-injected homepage URL) → selection turn (the LLM chooses candidate **ids**, never URLs) → a deduped, concurrent scrape set → one evidence item per scraped URL. Contexts are `site_map` and `metric_scrape`.

##### Traceflow
```text
phase-2 gate:  eligible ≠ ∅  AND  website_url ≠ None ?   NO → skip phase 2
phase2_loop(amenity)
  (a) MAP        [atom, context = site_map · app injects url = official homepage]
        firecrawl_map → link set → app shapes to (id,url) candidate list, ≤ 50, ids fresh per map
        failed / timeout → 1 retry → GIVE UP phase 2 (metrics stay on web evidence)
  (b) SELECTION TURN   LLM emits firecrawl_scrape calls, ONE page per eligible metric
        each call: id (never a URL) + required metric_label(s)
        guard: id ∈ issued set · ≥ 1 metric_label · every label ∈ eligible set
        invalid → 1 retry → still invalid → empty selection → web-only
  (c) DEDUP + RECORD
        1 collect (metric_label, id)   2 resolve id → real url   3 dedup by url (union of metrics)
        4 ceiling: > 8 distinct urls → drop surplus
        5 fetch once: ≤ 8 scrapes concurrent (Firecrawl sem + ≤ 10/min bucket);
          ok / empty / failed + 1 retry per url; failed → skip page; empty → continue, not retried
        6 record ONE evidence item (source_kind = scrape) carrying the union of requesting metrics
  no second triage · a successful phase 2 is not repeated
  every call_turn in (a)/(b): BREAKER CHECK first (open → ProviderError(stage=phase2, cause=circuit_open));
    MetricResolutionProviderError → phase 2 STOPS, passes it up (amenity ends in R3.M1.5)
```

##### Decisions — Generally mandatory
- **Termination.** Phase 2 follows its multi-step budget: `map` (1 call, one retry) → selection turn (invalid → one retry) → the deduped scrape set (one page per eligible metric, collapsed to **≤ 8 distinct URLs** per amenity, each scrape with one retry). `failed`, a timeout, or a guard rejection is retry-eligible; `empty` is terminal.
- **Two retry layers.** Gateway-internal retries (per-kind prerequisite above) do not count against the budget; the budget retry applies only after the gateway has returned a typed `failed`, and also covers guard rejections.
- **Concurrency.** Scrapes run concurrently with `gather` under the Firecrawl semaphore and the ≤ 10/min token bucket (C3.1.1); async-native, results in `tool_call_id` order.
- **Failure handling (D5).** Every tool call is shaped by R3.M1.2 into one `ok` / `empty` / `failed` `tool` message. A scrape that stays `failed` is skipped without failing the amenity, and tool-call failures never stop the amenity from reaching R3.M2. A `MetricResolutionProviderError` from a phase-2 `call_turn` (including `cause = circuit_open`) is different: phase 2 stops and passes it up, no `tool` message is appended, no budget retry is used, and the amenity ends per the R3.M1.4 Failure handling amenity-level outcome.
- **Conversation state.** Phase 2 reads and appends to the same shared message list as phase 1 and triage.

##### Decisions — Problem-specific nuances
- **Skip cases.** Phase 2 is skipped when no metric is phase-2-eligible (every metric `sufficient`, or every unresolved metric `experiential`), or `website_search_results.website_url` is `None` (R3.M1.3).
- **Instruction content.** Names the **phase-2-eligible** metrics and their `resolution_source.scrape_target` hints.
- **Tools.** `firecrawl_map` + `firecrawl_scrape`; the gateway operations, parsers, capability check and shape probe live in C3.1.1 (crawl retained there, unused by M3). The first phase-2 call is `firecrawl_map` with the app-injected homepage `url`; map returns links only, no content.
- **Candidate-list bounding.** The `map` result is trimmed to **at most 50** `(id, url)` pairs before the LLM sees it (a path pre-filter / `map search` may inform *which* 50). Ids are opaque, fresh per map result, selection-only.
- **Selection via id-indirection (per metric).** One `firecrawl_scrape` call per eligible metric: an `id` (**never a URL**) plus a required `metric_label` (≥ 1; a list is allowed when one page serves several). The guard validates the id against the issued set, requires ≥ 1 `metric_label`, checks each label against the phase-2-eligible set supplied in `validation_ctx` (an experiential or already-sufficient label → guard failure), dedups by resolved URL, enforces the **8-scrape ceiling**, and **substitutes the real URL verbatim** before the call reaches the gateway. URL text never passes through the model.
- **Dedup + fan-out cycle.** The six steps in the traceflow above are built exactly that way. This is the one place the many-to-many is resolved: **fetch is per URL, attribution is per metric.** A `failed` / `empty` fetch records no item.
- **Scrape evidence shape.** One scrape item per URL (`source_kind = scrape`) carrying the union of requesting metrics in `metric_labels`, stored once (see the `metrics_source_content` shape bullet above).
- **Best-effort (accepted constraint).** "One scrape per eligible metric" guarantees an *attempt*, not evidence. A metric can still end with no evidence when `map` surfaced no plausible page, the URL-only guess was wrong, or the page lacks the answer. Accepted (D5).
- **No second triage; a successful phase 2 is not repeated.**

## R3.M1.5 — Plan Work Items and Run Amenity Pipelines

**Goal.** `run_specific_metric_resolution` on `SpecificMetricResolution` builds one work item per `(category_id, place_id)` in `state.discovered_places` whose category has ≥1 `specific_metrics` entry (RC7). Each item takes `category_id`, `taxonomy_node`, `depth`, `specific_metrics` from the category's `CategoryMetricPlan`, and `place_id` from the `discovered_places` key. It then runs the **R3.M1.3 discovery batch** over all work items (concurrent, behind a hard barrier) to populate each work item's `website_search_results` (RC8: URL first, then the loop), and only after that barrier returns runs the amenity pipelines (R3.M1.4) concurrently under bounds, passing each finished conversation + `metrics_source_content` to the per-amenity R3.M2 steps (R3.M2.2–R3.M2.4) as it completes. Each pipeline returns its `SpecificMetricsRecord` and writes no shared state. The `gather` waits for every pipeline before R3.M2.5 runs.

**Problem.** M1 records carry no metric info (metrics live on `CategoryMetricPlan.specific_metrics`). Eligibility/identity/sharing across categories must be defined. Many amenities run together → concurrency needs a bound and one failure must not cancel others. R3 is a new class: the LLM caller and MCP gateway are injected into `SpecificMetricResolution`, and `run_specific_metric_resolution` is its new entry method (before the promotion, no R2 class held these).

**Finalized approach — Approach 1: pre-indexed join + `gather`.**
Build `plan_index` (`category_id` → `CategoryMetricPlan`) once, derive the work-item list from it + `state.discovered_places`, then run all amenity pipelines with `asyncio.gather(*tasks, return_exceptions=True)`. The `gather` **is** the hard barrier before R3.M2.5; `return_exceptions=True` together with each pipeline catching its own failure (returning a `SpecificMetricsRecord` whose metrics are `unresolved`, D5) gives **per-amenity failure isolation**. Chosen for consistency with R3.M1.3's discovery batch (`gather`+semaphore) and R3.M2.5's "combine once after the `gather`."

**Trace flow (`run_specific_metric_resolution`):**
```
run_specific_metric_resolution(state)                         [R3.M1.5, method on SpecificMetricResolution]
│
├─ open gateway sessions (Parallel + Firecrawl)          [C3.1.1 — session scope = method]
│
├─ STEP 1  Build plan_index  (category_id → CategoryMetricPlan)      ── once
│
├─ STEP 2  Derive work items  = eligible (category_id, place_id)      [RC7]
│          from state.discovered_places × categories with ≥1 specific_metrics
│          work_items = [ (cat, place, taxonomy_node, depth, specific_metrics), ... ]   (N items)
│
├─ STEP 3  DISCOVERY BATCH  (R3.M1.3)        ── Stage-0 sync pre-pass → fan out declined only, hard barrier
│          inputs per wi ← PredefinedMetricsRecord = state.predefined_records[cat][place]
│                          (name, website, address verbatim → LLM)
│          Stage-0 pre-pass (sync, ALL wi): official → website_search_results[..]=google (no task)
│                                           else     → declined += wi  (gate error → declined)
│          tasks = [ discover_search(wi) for wi in declined ]      # Stage 1 only; declined subset
│          await asyncio.gather(*tasks)        async with discovery_sem (Parallel pool)
│            each task: breaker_open? → none (no search, no selection turn)
│            LLM ProviderError → none (amenity still runs); availability → breaker counter +1
│          → website_search_results[(cat,place)] = {website_url|None, origin}   (complete for all N)
│          ╌╌╌ barrier waits on declined only; pass-items already written → ALL verdicts ready (RC8) ╌╌╌
│
├─ STEP 4  AMENITY PIPELINES  (R3.M1.4 + R3.M2.2–R3.M2.4)    ── concurrent, under bounds
│          tasks = [ pipeline(wi, website_search_results[key]) for wi in work_items ]
│          results = await asyncio.gather(*tasks, return_exceptions=True)
│
│   each pipeline(wi)  ── runs independently, writes NO shared state ───────────────┐
│   │                                                                               │
│   │  phase1_loop  → triage → (cond.) phase2_loop            [R3.M1.4]              │
│   │     web_search turns     map→select→scrape turns                              │
│   │     (LLM permit per call; Parallel/Firecrawl permits per tool call)           │
│   │  builds its own conversation + metrics_source_content                         │
│   │  → R3.M2.2 resolution turn → R3.M2.3 conform → R3.M2.4 provenance                │
│   │  every LLM call: BREAKER CHECK first (open → ProviderError cause=circuit_open) │
│   │                                                                               │
│   │  try:     return SpecificMetricsRecord(resolved/unresolved metrics)           │
│   │  except MetricResolutionProviderError as e:                                   │
│   │           remaining steps skipped · evidence discarded                        │
│   │           return SpecificMetricsRecord(all unresolved(resolution_call_failed))│
│   │           log stage + cause · cause = availability → breaker counter +1      │
│   │  except:  return SpecificMetricsRecord(all metrics unresolved)   [D5]         │
│   │           ── failure caught INSIDE the task → isolated, siblings unaffected   │
│   └───────────────────────────────────────────────────────────────────────────── ┘
│
│          ╌╌╌╌╌╌╌╌╌  HARD BARRIER  ╌╌╌╌╌╌╌╌╌
│          gather returns only when ALL N pipelines have finished
│          (a "failure" still finished — it returned a record; D5)
│          return_exceptions=True → an unexpected raise comes back as a value,
│                                    not a cancel of the other tasks
│
├─ STEP 5  Post-gather sweep                               ── single-threaded, after barrier
│          for r in results:
│             if isinstance(r, Exception):  → synthesize all-unresolved record  [D5 safety net]
│             else:                          → r is a SpecificMetricsRecord
│          RUN-LEVEL RAISE: no pipeline completed its LLM steps without a provider error
│             (all failed / breaker-skipped / mix) → raise MetricResolutionProviderError
│             (sessions still close — CLOSE runs in finally)
│
├─ STEP 6  R3.M2.5  COMBINE  (run-level, runs exactly once)
│          store state.specific_records[cat][place] = record
│          pair with state.predefined_records → AmenityMetricsRecord
│          build versioned AmenityMetricsSet (1.0) → state.amenity_records
│          (N = 0 → set still built, every specific = None)
│
└─ close gateway sessions (aclose)                         [C3.1.1]
```
Two separate `gather` barriers: STEP 3 (discovery must finish before any pipeline — RC8) and STEP 4 (all pipelines must finish before R3.M2.5). Failure isolation is two-layered: each pipeline catches its own failure and returns an unresolved record (primary, D5); `return_exceptions=True` is the backstop for an *unexpected* raise, which the STEP 5 sweep converts into an all-unresolved record. No shared-state writes occur inside STEP 4 — pipelines return records by value; the only run-level writes happen in STEP 6, after the barrier.

**Decisions — generally mandatory**
- **Placement.** `run_specific_metric_resolution` is a method on `SpecificMetricResolution`, called after `run_result_attachment`.
- **Wiring.** Shared caller and gateway injected at the composition root (`create_amenity_search`). `aclose()` closes the gateway. The caller is closed once, by its owner.
- **Bounds.** Per-server semaphores — **Parallel** (search, shared by the discovery batch and phase 1) and **Firecrawl** (`map`/`scrape`, replacing the old crawl semaphore) — plus an LLM-call bound and a cap on amenity pipelines in flight. Starting values configurable, not measured. A separate **per-amenity ceiling of 8 distinct scrapes** (enforced by the R3.M1.1 guard) bounds Phase-2 fan-out independently of the global Firecrawl semaphore.
- **Failure isolation.** One amenity's failure doesn't cancel others. The run raises in two cases only: a gateway-level failure (cannot connect, expected tool missing), and the provider-failure run-level raise below.
- **Provider-failure handling (pipeline catch).** The pipeline catches `MetricResolutionProviderError` from any of its LLM steps (phase 1, triage, phase 2, resolution) and returns a `SpecificMetricsRecord` with every metric `unresolved(resolution_call_failed)`; remaining steps are skipped and gathered evidence is discarded. `stage` and `cause` are logged, not stored on the record. Full rule in R3.M1.4 "Failure handling (D5)."
- **Provider-failure circuit breaker (run-scoped).** Created at method start, shared by the discovery batch and every amenity pipeline.
  - *Counter.* Goes up by 1 for each `cause = availability` failure from an amenity pipeline **or** a discovery LLM call (tool turn or selection turn), and resets to 0 when any LLM call succeeds. Safe without a lock because everything runs on one event loop (C3.1.1). Amenities run concurrently, so "in a row" means failures with no LLM success in between, in completion order.
  - *Trip.* The breaker opens when the counter reaches `N` (configurable, default 3) and stays open for the rest of the run.
  - *Check point.* Immediately before every `call_turn` and structured call (phase 1, triage, phase 2, resolution), after the LLM-call permit is acquired, and before each discovery coroutine starts Stage 1. Pipelines already in flight therefore stop at their next LLM call.
  - *When open (amenity step).* The call isn't made. The step raises `MetricResolutionProviderError(stage = <step>, cause = circuit_open)`, which the pipeline catch handles. Phase 1 starts with `call_turn`, so an amenity that hasn't started yet stops at its first check, before any search or Firecrawl call.
  - *When open (discovery).* The work item skips its search and selection turn and gets a `none` result (R3.M1.3).
  - *Labelling.* Breaker-skipped amenities use reason `resolution_call_failed` with `cause = circuit_open`. No new unresolved reason is added, so the record schema doesn't change.
  - *Not counted.* `content` and `circuit_open` failures never move the counter.
- **Run-level raise (provider failure).** After the STEP 5 sweep, the run raises `MetricResolutionProviderError` when no amenity pipeline completed its LLM steps without a provider error (every amenity failed, was breaker-skipped, or a mix). Otherwise it returns records, with the failed and skipped amenities unresolved. With no work items, nothing is attempted and the run does not raise. Replaces the former R3.M2.2 rule ("raised only if the chain fails for every attempted amenity").

**Decisions — problem-specific**
- **Eligibility.** Non-empty `specific_metrics` at any depth. A `basic_profile` category with none yields no work item.
- **No narrowing step.** M3 runs on all M1 records. Candidate selection (R3) not implemented; may move ahead of M3 later.
- **Pre-loop discovery batch (R3.M1.3).** Before any amenity pipeline starts, `run_specific_metric_resolution` runs the discovery batch over all work items (a **synchronous Stage-0 pre-pass over all items**, then `asyncio.gather` + `discovery_sem` over the **gate-declined subset only**, hard barrier) and populates each work item's `website_search_results`. Pipelines start only after the barrier returns. Each discovery reads its inputs (`name`, `website`, and the full `address` string, passed to the LLM verbatim — not parsed) from the work item's **`PredefinedMetricsRecord`** at `state.predefined_records[category_id][place_id]` (R3.M1.3 "Input source").
- **Two categories, one place.** Two work items (metrics differ). Each runs its **own** discovery (R3.M1.3 — no dedup, no single-flight) and its **own** Phase-2 `map`/`scrape` — **there is no shared crawl cache**. (Supersedes the draft's "share one crawl via the cache"; **D4 revised** accordingly — no shared crawl per site.)
- **Session lifetime.** Gateway sessions open at method start and close at its end — covering both the discovery batch and the amenity pipelines.
- **Logging.** Pipeline start/end, tool-call outcome and duration, triage result, phase-2-skipped, provider failures (`stage` + `cause`), breaker opened — without keys or evidence text.

---

# Mechanism R3.M2 — Resolution

## R3.M2.1 — Define the Resolution Schema and Instruction

**Goal.** One strict JSON schema for the resolution turn + one instruction module stating decision rules. Schema returns one entry per submitted metric label. `build_resolution_instruction(json_schema)` produces the final-turn instruction.

**Problem.** No output wire contract for M3. Contradiction/sufficiency/quoting rules exist only as prose. Both providers apply strict schema limits; a static schema can't carry per-metric enums. The resolution turn runs after tool results that may contain untrusted text.

**Finalized approach — Approach 2: one static schema with a typed-union `final_value`.**
A single static schema (not generated per amenity). `final_value` is a **typed union of `string | number | boolean | null`**, covering the four shapes a metric value can take (text, number, boolean, or no value). Per-metric **enum membership, `unit`, and `value_type`** conformance is **not** in the schema — a static schema can't carry per-metric enums, so that stays a **code check in R3.M2.3**. Fields: `metric_label`, `web_value`, `scrape_value`, `relation`, `final_value`, `basis`, `verification_met`, `evidence`.

**Decisions — generally mandatory**
- **Schema limits.** All keys required, closed objects, closed enums, no `minLength`/`minItems` — the same limits as Mechanism 6.
- **Builder pattern.** `build_resolution_instruction(json_schema)` in a dedicated instruction module, as in earlier mechanisms.
- **Examples.** Worked examples in the instruction are not reused as a sample-runner seed.

**Decisions — problem-specific**
- **Value typing (Approach 2).** `final_value` is the typed union `string | number | boolean | null`. `web_value` and `scrape_value` are **descriptive strings the LLM writes** (they don't map to any existing data-object field, so no per-metric typing is needed on them). `verification_met` is boolean; `relation` / `basis` are the fixed closed enums below; `evidence` is a structured object. Per-metric `enum`/`unit`/`value_type` conformance of `final_value` is deferred to R3.M2.3 (code).
- **Field order.** `web_value` and `scrape_value` before `final_value`, so both source values are extracted before the commit.
- **Contradiction rule (D7).** A non-null `scrape_value` is the `final_value`, even contradicting `web_value`. `web_value` used only when `scrape_value` is null.
- **Verification rule.** `verification_met` false when evidence doesn't satisfy the metric's `verification` text; `final_value` then null.
- **Google reviews as a fallback value source (verification-gated — finalized).** Reviews are already supplied to the resolution turn as a labeled block (**not** a tool, never fetched; the tool catalog and `resolution_source` are unchanged). Instruction rule: *"Resolve each metric from the tool evidence (web/scrape) first, applying the metric's `verification` rule. Set `final_value` from the Google-reviews block **only when no tool value satisfies that rule** (tools returned nothing, or only evidence that fails verification) **and** a review quote does satisfy it. Cite `source=google_reviews`."* The per-metric **`evidence_class` is the factual/experiential switch** (set at Mechanism 6, read directly — never parsed from text): `factual` rejects reviews; `experiential` (equivalently, a `review_target` present) lets a review pass. A review-sourced value sets `basis=google_reviews` and is `single_source` (R3.M2.4). Tools may still resolve experiential metrics when a tool value passes the experiential verification — reviews fill only the gaps (not "experiential ⇒ reviews-only"). **Safety net:** a metric with **no `review_target`** (i.e. not `experiential`) is reviews-blocked by default — reviews stay ineligible unless `evidence_class` is `experiential`. **RC10 (revised):** the experiential `review_target` is a reviews **reading hint**, not a new tool — reviews are still read, never fetched; reviews remain a resolution-time fallback gated by `evidence_class`.
- **Relation / basis enums (trimmed, + reviews).** `relation`: `agree`, `refined_by_scrape`, `conflict`, `none`. `basis`: `web`, `scrape`, `both`, `google_reviews`, `none`. `web_only`/`scrape_only` are dropped from `relation` (a single-source value is recoverable from `basis` = `web`/`scrape`); `verification_rule` is dropped from `basis` (the "why null" is carried by `verification_met` + the downstream `unresolved_reason`); **`google_reviews` is added to `basis`** for a value set from the reviews fallback above. **`relation = none`** means *no cross-source relationship* — fewer than two source values are present (only-web, only-scrape, or neither; a review-only value is also `relation=none`); it must be read **together with `basis`**, and the instruction must define it this way so the model doesn't conflate "no relationship" with "no value." The R3.M2.3 consistency check reads `relation` + `basis` together.
- **Evidence items.** `source` (`web`/`scrape`/`google_reviews`), `url` (string|null), verbatim `quote`.
- **No numeric confidence.** Trust carried by `support` (R3.M2.4) and the quotes.
- **Untrusted content rule.** Instructions in tool results are ignored. Amenity Google reviews supplied as a labeled block.

> *Schema approach finalized: Approach 2 (static schema, typed-union `final_value`).*

## R3.M2.2 — Run the Resolution Turn and Validate the Body

**Goal.** Build the resolution turn from the amenity's `metrics_source_content` — **not** from the tool-call thread. For each submitted metric, present that metric's evidence bucket (its items in `metrics_source_content` — those whose `metric_labels` contains the label) plus the amenity-level Google-reviews block when reviews exist (R3.M2.1, shown to every metric). Append the resolution instruction and this evidence, then call the shared caller with the resolution schema and no tools (reviews are a labeled block, not a tool). Return a body matching the schema and covering exactly the submitted labels, or a typed per-amenity failure. Skip the call only when no metric has any usable evidence (see Skip rule).

**Problem.** The call can fail (provider error, truncation) or return an invalid body. The body can miss/repeat/add a label. D5: one amenity's failure must not stop the run. A no-evidence call is cost with no output.

**Three common approaches**
1. Model validation, then label-set check (whole body rejected on any mismatch).
2. Per-entry validation (valid entries kept; missing/extra/invalid → only those labels unresolved).
3. Hand-written dict validator, then label-set check.

**Decisions — generally mandatory**
- **Fallback rule.** The shared caller falls back on provider errors and truncation; never for an invalid body.
- **Typed errors.** Validation failures carry `stage` and a reason (`schema` or `label_coverage`).
- **Logging.** `metric_resolution.validated` and `metric_resolution.rejected`.

**Decisions — problem-specific**
- **Evidence source & shape (finalized).** Resolution reads the amenity's `metrics_source_content`, a **normalized evidence set** of items `{ evidence_id, source_kind ∈ web|scrape|google_reviews, url, shaped_text, retrieved_at, metric_labels }` (shape defined in R3.M1.4), with **Google reviews** as one amenity-level item (empty `metric_labels`) passed to **every** metric. The prompt is assembled **per metric** from that metric's bucket — the items whose `metric_labels` contains the label (+ reviews) — so the model sees each metric's own evidence instead of one flat pool and does not re-derive cross-metric relevance semantically. Same-URL/different-`shaped_text` web items stay distinct and never collapse. The tool-call thread is **not** the resolution input.
- **Skip rule (deterministic structural gate — finalized).** Run the call whenever the amenity has **any** evidence to reason over: at least one metric has web/scrape evidence **or** a Google-reviews block exists for the amenity. Skip only when **both** are absent (no web/scrape evidence for any metric **and** no reviews block). The gate is **purely structural** — R3.M2.2 never reads `verification` text to judge review eligibility; when reviews exist the call runs and the **resolution LLM** applies each metric's per-`verification` review-eligibility rule (R3.M2.1 is the single authority for that semantic judgment). The gate errs permissive by design: skipping too eagerly would emit a false `no_evidence`, whereas running a call that happens to resolve nothing (e.g. reviews present but every metric factual) costs only one bounded call. A skipped amenity's metrics are all `unresolved(no_evidence)`.
- **Failure result (D5, D6).** A provider-chain failure or invalid body for one amenity → `value = None`, `status = unresolved`, reason `resolution_call_failed` or `resolution_body_invalid`. Run continues. The resolution call checks the circuit breaker first; a provider failure here (including `cause = circuit_open`) follows the R3.M1.4 amenity-level outcome.
- **Run-level raise.** Defined once in R3.M1.5 "Run-level raise (provider failure)."
- **Default carried from spec.** Label coverage rejects the whole body, no fill (Approach 2 would change this default).
- **Prompt size.** The resolution prompt is the per-metric evidence buckets (+ reviews) from `metrics_source_content`, not the full thread; its size rests on the R3.M1 caps that bound what the buckets contain. No separate token accounting.

> *Validation approach (1 / 2 / 3) is open for discussion — note the whole-body-reject default favors Approach 1/3.*

## R3.M2.3 — Conform Values and Apply the Verification Gate

**Goal.** For each entry in a valid body, conform `final_value` to the metric's `value_type`, `unit`, `enum_values`. Apply the verification gate and check that reported relation/basis are consistent with D7. Each metric ends as a conformed candidate or `unresolved` with a reason.

**Problem.** A static schema can't enforce per-metric enums/units/types. A model can return an out-of-definition value. D7 makes scrape win, and the verification rule still gates whether any value commits. Invalid values must not reach M4 looking like facts.

**Three common approaches**
1. Ordered guard functions per `value_type` (first failing check sets the reason).
2. Dynamic Pydantic model per metric (built from each `MetricSpec`).
3. Table-driven conformer registry (`value_type` → conformer, shared normalization helpers).

**Decisions — generally mandatory**
- **No repair.** No nearest enum, no unit conversion in code, no default. An invalid value → `unresolved`.
- **Type rules.** `number_with_unit` parses as a plain number, unit is the spec's `unit` (model told to convert). `boolean` is `true`/`false`. `enum` matches a member case-insensitively, stored in the member's spelling. `date_time` is ISO-8601.
- **Guard order.** Conformance → verification gate → relation/basis check.

**Decisions — problem-specific**
- **Verification gate.** `verification_met = false` → `unresolved(verification_unmet)`, even when a scrape value exists. The scrape value decides which value wins; it does not commit a value that fails verification.
- **Scrape override check.** When `scrape_value` is non-null, `final_value` must equal it after normalization. A mismatch means the model broke D7 → `unresolved(basis_inconsistent)`, nothing repaired in code. Adds one reason to the output contract (recorded by R3.M2.5).
- **Unresolved reasons set here.** `type_violation`, `enum_violation`, `verification_unmet`, `basis_inconsistent`.

> *Conformer approach (1 / 2 / 3) is open for discussion.*

## R3.M2.4 — Verify Provenance Against `metrics_source_content`

**Goal.** Check each quote in a resolved metric against `metrics_source_content`. Drop quotes that fail. A resolved value with no surviving quote → `unresolved(quote_unverified)`. Compute `support` and `as_of` from surviving quotes. Build one `ResolvedMetric` per metric and the amenity's `SpecificMetricsRecord` (identity fields from the work item; `specific_metrics` keyed by label), and return the record. Every path ends in a record (success, no-evidence skip, failed call, invalid body). The pipeline writes nothing to shared state.

**Problem.** A model can quote text not in the evidence. Pages/results can carry planted instructions/claims. The later assessment needs to know whether a value rests on both sources or one. A value needs an as-of time (hours, prices, ratings change).

**Three common approaches**
1. Normalized substring match (whitespace+case normalized; quote must be a substring of the cited-URL text in `metrics_source_content`).
2. Fuzzy match (similarity threshold against a window).
3. Span references (LLM returns source id + char span; code slices and compares).

**Decisions — generally mandatory**
- **Normalization.** Whitespace collapse + case folding. No other rewriting.
- **`metrics_source_content` content.** The shaped text actually sent to the LLM (R3.M1.2), stored in the normalized evidence set (R3.M1.4): one item per distinct `(source_kind, url, shaped_text)`, attributed to metrics via `metric_labels`, with the `google_reviews` item carrying none.
- **URL rule.** A quote's URL must be one of the URLs in **that metric's** `metrics_source_content` bucket (or the amenity-level reviews block).

**Decisions — problem-specific**
- **`support`.** `both_sources` when surviving quotes cite both `web` and `scrape`; otherwise `single_source`. `google_reviews` alone is `single_source`.
- **Google reviews.** Can be cited as supporting text; never count as the second source.
- **`as_of`.** Latest `retrieved_at` among the `metrics_source_content` entries the surviving quotes cite.
- **Failure result.** A resolved value with no surviving quote → `unresolved(quote_unverified)`, `value = None`.

> *Provenance match approach (1 / 2 / 3) is open for discussion — the draft decisions describe Approach 1.*

## R3.M2.5 — Combine Predefined and Specific Records Into the Versioned Amenity Metrics Set

**Goal.** Run-level step of R3.M2, once, after the `gather`. Takes all returned `SpecificMetricsRecord`s (built per amenity in R3.M2.4), stores them in `state.specific_records`, pairs each with its `PredefinedMetricsRecord` from `state.predefined_records` by `(category_id, place_id)` into an `AmenityMetricsRecord`, and writes the versioned `AmenityMetricsSet` (contract 1.0) to `state.amenity_records`. Applies no `null_policy`.

**Problem.** Predefined and specific metrics come from different sources and two record types; downstream needs one object per place holding both. M3 has no output location; RC9 (revised) gives a separate `SpecificMetricsRecord`, and this is where the two halves meet. `AmenityRecordSet` removed → the single versioned envelope is built here. D5 requires every eligible amenity present in the combined set. M4 must apply `null_policy` and carry provenance without re-deriving them.

**Three common approaches**
1. Combine once after all pipelines (lookup of returned records by key; iterate `state.predefined_records`; build `AmenityMetricsSet` once).
2. Merge as pipelines finish (each merges into a shared set by key).
3. Extend the M1.3 assembly function (`assemble_amenity_records` takes M3 results as a second input).

**Decisions — generally mandatory**
- **Approach.** Approach 1 chosen. Run-level combine once, after the `gather`. Pipelines return records and write no shared state, so no two tasks write shared state at once.
- **Contract version.** The combined `AmenityMetricsSet` is the only versioned object, `contract_version "1.0"` (module constant `AMENITY_METRICS_CONTRACT_VERSION`). `PredefinedMetricsRecord`, `SpecificMetricsRecord`, `AmenityMetricsRecord` carry no version. `AmenityRecordSet` removed.
- **Immutability.** All records and the set are frozen.
- **State fields.** `state.predefined_records` (M1.3 output) and `state.specific_records` (stored here) are plain nested dicts keyed `category_id` then `place_id`. `state.amenity_records` holds the `AmenityMetricsSet`, `None` until this step runs.
- **Pairing by key.** `specific` looked up by `(category_id, place_id)`. Both records take `category_id`, `taxonomy_node`, `depth` from the same `CategoryMetricPlan`, and `place_id` from the `discovered_places` key (same source M1.3 uses) → no separate consistency validation.
- **Not applicable vs attempted.** A place whose category has no `specific_metrics` → `specific = None`. A place whose pipeline failed → `SpecificMetricsRecord` with every metric `unresolved`. With no work items at all, the set is still built with every `specific = None`.

**Decisions — problem-specific**
- **`SpecificMetricsRecord` fields.** `category_id`, `taxonomy_node`, `depth`, `place_id` + `specific_metrics: dict[label, ResolvedMetric]`.
- **`AmenityMetricsRecord` fields.** `predefined: PredefinedMetricsRecord` (always present) and `specific: SpecificMetricsRecord | None`.
- **`AmenityMetricsSet` fields.** `contract_version: str` and `records: dict[category_id][place_id] → AmenityMetricsRecord`.
- **`ResolvedMetric` fields.** `label`, `status` (`resolved`/`unresolved`), `value` (float/bool/str/None), `unit`, `support`, `evidence` (source, url, quote, `retrieved_at`), `as_of`, `unresolved_reason`.
- **Unresolved reasons.** `no_evidence`, `verification_unmet`, `type_violation`, `enum_violation`, `quote_unverified`, `basis_inconsistent`, `resolution_call_failed`, `resolution_body_invalid`. `resolution_call_failed` covers any LLM provider failure in the amenity pipeline, including a breaker skip; the failing step and cause are in the logs, not the record (R3.M1.5).
- **Null-policy boundary.** R3.M2 emits `resolved`/`unresolved(reason)`, `value None` when unresolved. C4.1 alone maps to `null`/`"unknown"` via `null_policy`.
- **Downstream changes.** C4.1's "inline enforcement at R3.M2" wording no longer matches. C4.2 consumes `AmenityMetricsSet` (pairing already done here) → its "merge" goal needs rewording; it must carry `support`, `evidence`, `as_of` into the assembled record.
- **Other changes outside M3.** M1.3 now writes `state.predefined_records` as a plain dict (no envelope/version; spec updated in `deep_search_context.md`). Code: rename `AmenityRecord` → `PredefinedMetricsRecord`, remove `AmenityRecordSet`, add new record types, add two state fields, retype `amenity_records`.
- **Metric identity.** `(category_id, place_id, label)`. `label` unique per category (Mechanism 6 rule K5).

---

## Open verifications (before building)

1. **Resolved for M3 (C3.1.1).** Parallel `web_search` MCP output verified (mirrors REST: `results[].{url, title, excerpts[]}`; the existing parser handles it). Firecrawl map/scrape output is **MCP server 3.x JSON output** (top-level `markdown`, `metadata.sourceURL`, map `links`; `structuredContent` preferred, JSON text block accepted); a **live run confirmed the hosted `/v2` endpoint returns that shape**, so `open()` runs the `tools/list` capability check only — **the connect-time map+scrape probe is removed** — and a wrong shape, if it recurs, surfaces as a per-call `ToolFailure(unparseable)` on the first real call (C3.1.1).
2. The exact `firecrawl_crawl` arguments / polling behavior — **retained-crawl path only, not an M3 blocker** (M3 uses map/scrape) (C3.1.1).
3. V2a: ten concurrent `web_search` calls on one Parallel `Client` return matching results, one timeout doesn't fail the others (C3.1.1).
4. V2b (M3 path): several `scrape_page` calls on one Firecrawl `Client` after a `map_site` return matching results; one scrape timeout doesn't fail the others; the session stays usable (C3.1.1). Crawl-interference checks apply only to the retained crawl path.
5. Whether the crawl job id is available when a crawl times out — **retained-crawl path only, not an M3 blocker** (C3.1.1).
6. **Resolved (C3.1.2 / R3.M1.1).** OpenAI (Chat Completions) and Groq both accept replayed tool-call history; the hard rule is one `tool` message per `tool_call_id` (satisfied by R3.M1.2's exactly-one-message rule). Caveat captured in R3.M1.1: a call to a tool not in `request.tools` must be sanitized out of the persisted history or Groq rejects the next request. (`tools` + `response_format` in one request is moot — C3.1.2 keeps them separate.)
7. Firecrawl and Parallel rate limits for the plans in use (C3.1.1).

---

## Open decision points for discussion

These are the places the draft still leaves a choice (everything else is a locked or finalized decision):

- **C3.1.1** — ✅ **FINALIZED** (see section). Gateway **extended** with `map_site` + `scrape_page` (crawl **retained**, unused by M3); capability check requires map + scrape only (crawl unchecked); map/scrape parsers (scrape → top-level `markdown` + `metadata.sourceURL`; map → link objects, string-form tolerated); **connect-time shape probe**; `structuredContent` decode attribute confirmed; Parallel web path verified. (C3.1.2 is implemented and matches spec.)
- **R3.M1.3** — ✅ **FINALIZED** (see section). Approach 2 (LLM selection), binary host rule, app-injected crawl URL / host-clamp removed, `gather`+semaphore batch discovery, empty/failed + Pydantic-retry rules, Google-URL officiality gate (`official_url_gate`: `tldextract` SLD-match + exact-set denylist fast-reject, pinned offline PSL, strict by asymmetry), selection-turn **candidate id-indirection** (anti-hallucination; LLM returns a `selected_id`/`none`, app resolves, verdict validated at the body — not the tool-call guard) + `state.discovery_search_results` storage for eval. *Resolved:* postal-code handling is LLM-instructed — full `address` passed verbatim, use postal code only, degrade to locality/name when absent; app parses nothing.
- **R3.M1.4** — ✅ **FINALIZED** (see section). Split loops (`phase1_loop → triage → phase2_loop`); triage via a separate strict-schema no-tools request; loop decisions aligned to R3.M1.1/R3.M1.2/R3.M1.3; `metrics_source_content` shape fixed. **Phase-2 scrape redesign finalized:** per-metric scrape (one page per phase-2-eligible — unresolved + `factual` — metric), `metric_label` required (≥1, multi allowed), explicit dedup + fan-out (fetch per URL, attribute per metric), hard ceiling of **8** distinct scrapes/amenity, candidate list bounded to **50**; best-effort accepted (attempt ≠ guaranteed evidence). **Failure handling finalized:** tool-call failures continue; an LLM provider-chain failure stops the step and ends the amenity (`resolution_call_failed`, evidence discarded); `cause` on the error (C3.1.2); run-level circuit breaker and run-level raise (R3.M1.5).
- **R3.M1.5** — ✅ **FINALIZED** (see section). Approach 1 (pre-indexed `gather`, `return_exceptions=True`); hard barrier before R3.M2.5; per-amenity failure isolation; pre-loop discovery batch; no shared crawl (D4 revised); provider-failure circuit breaker (counts `availability` only, default N = 3) and run-level raise when no pipeline completes its LLM steps.
- **R3.M2.1** — ✅ **FINALIZED** (see section). Approach 2: one static schema with a typed-union `final_value` (`string|number|boolean|null`); descriptive fields as strings; per-metric enum/unit/type conformance deferred to R3.M2.3. Enums trimmed (`relation`: 4; `basis`: 5, incl. `google_reviews`); **Google reviews added as a verification-gated fallback value source** (eligibility gated by `evidence_class`; RC10 revised).
- **R3.M2.2** — evidence source ✅ **finalized**: resolution reads the normalized-evidence-set `metrics_source_content` (reviews as an unlinked item; per-metric buckets derived via `metric_labels`), not the thread. **Body validation** still open: whole-body reject / per-entry / dict validator (default favors whole-body reject).
- **R3.M2.3** — conformer: ordered guards / dynamic model / registry.
- **R3.M2.4** — provenance match: substring / fuzzy / span (draft decisions describe substring).

---

## Carried forward under the R3 promotion

This mechanism is being promoted to its own responsibility, **R3 — Specific Metric Resolution**
(see `R3_Specific_Metric_Resolution_proposal.md`). The promotion closes **none** of the decisions
left open above; each stays open and owned by its sub-component:

- **R3.M1.3 — postal-code handling (resolved: instructed).** The full `address` is passed to the LLM
  verbatim; the instruction directs it to use only the postal code for locality scoping (the app parses
  nothing) and to degrade `postal code → locality/city → name-only` when Google returns none. The earlier
  inject-vs-instruct choice is settled on *instruct*.
- **R3.M2.2 — resolution body validation.** Whole-body reject / per-entry / hand-written dict
  validator (default favours whole-body reject).
- **R3.M2.3 — value conformer.** Ordered guard functions / dynamic per-metric Pydantic model /
  table-driven registry.
- **R3.M2.4 — provenance match.** Normalized substring / fuzzy / span references (draft decisions
  describe substring).

**ID-rename (planned task, not a reopened decision).** On promotion, the `C3.x` sub-component IDs
in this document are renamed to the R3 mechanism IDs — evidence acquisition → `R3.M1.x`, resolution
→ `R3.M2.x` — as a mechanical sweep **before** implementation, so references stay consistent across
this spec and `deep_search_context.md`.
