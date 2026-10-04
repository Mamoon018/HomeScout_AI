## The issue: how to run concurrent MCP calls in the C3.1.1 gateway

**Setup**
- The gateway calls two hosted MCP servers: `web_search` on Parallel, and `firecrawl_crawl` on Firecrawl.
- Each server has its own URL, bearer key, and session, so there is one client per server.
- Sessions open at the start of `run_llm_metric_resolution` and close at its end, in the same task.
- Throughput is capped by a semaphore per server.

**The question**
Can many concurrent calls safely share one session per server, or does the design need something more (a session pool or extra sessions)?

**Why it came up**
- The plan listed an open verification: is concurrent `call_tool` on one `ClientSession` safe?
- Its fallback was a session pool sized to the semaphore.
- The concern was that a long `firecrawl_crawl` could stress or block a shared session.

**What we established**
1. **Multiplexing is the protocol's design.** MCP uses JSON-RPC request ids, so replies are matched to the right call. Concurrent asyncio tasks on one session are the intended pattern.
2. **Supporting evidence is indirect.** A FastMCP maintainer says sharing one client across asyncio tasks in one loop is fine. FastMCP is a different library from `mcp.Client`, so this points a direction without confirming it.
3. **The boundary matters.** Sharing across threads or across event loops is not safe. The gateway should be created, used, and closed on one loop.
4. **Throughput is governed server-side.** Firecrawl limits depend on the plan, and Parallel limits depend on the key tier. More sessions add no capacity, so a pool does not help throughput.
5. **Parallel `session_id` is unrelated to the MCP session.** It is a tool argument used for free-tier rate limiting and log correlation. One UUID per run is a safe default.
6. **Crawl behavior.** `firecrawl_crawl` polls internally and returns final data. It also returns an id usable with `firecrawl_check_crawl_status`. A timed-out crawl should be re-checked, not repeated.

**A correction along the way**
- I had worded the verification as running a search and a crawl "on one `Client`." That was wrong.
- The two tools live on different servers, so they never share a client.
- Sharing only happens within one server.

**What remains uncertain**
- Whether a slow crawl delays other calls on the same Firecrawl session. This depends on server behavior, not client design.
- How cancellation or a timeout on one call affects the others.
- What happens when a session expires or drops, since every in-flight call would fail together.

**Resulting position**
- **Default:** one session per server plus a per-server semaphore.
- **Pool:** dropped as a default. The only fallback is two fixed-role Firecrawl sessions, one for crawls and one for quick calls, with no borrow or return logic.
- **Verifications, split per server:**
  - V2a (Parallel): about ten concurrent `web_search` calls on one `Client`. Check that results match their requests and that one timeout leaves the others working.
  - V2b (Firecrawl): a slow crawl alongside `firecrawl_check_crawl_status` and a second crawl. Check that fast calls return first, results stay separate, and the session survives a forced timeout.
- **Contract line to add:** the gateway lives on a single event loop and is not shared across threads.

**Next step**
Run V2a and V2b. Also check the official MCP Python SDK docs or source for `ClientSession` concurrency guarantees, since all the evidence so far is indirect.