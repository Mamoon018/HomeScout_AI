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
