



1. Phase-1 Loop
Goal
For one amenity, search every metric (factual and experiential alike) with one web_search per metric, all in the first turn, then run at most one retry turn covering only the metrics whose search failed. Each turn appends its tool messages to the amenity's single shared conversation and records web evidence items into metrics_source_content.

Problem it aims to solve
Nothing drives the assistant → tool-call → tool-result cycle. Phase 1 needs defined rules for termination, per-metric budgets and retries, attributing each search to the metric it serves, mixing on-site and off-site queries without collapsing web evidence onto the official site, keeping a tool failure from stopping the amenity or the run, and defining what happens when the LLM provider chain itself fails.

Finalized approach
A dedicated phase1_loop function that runs the shared R3.M1 tool-turn cycle (catalog → call_turn → guard → gateway → shape) with context = metric_web_search, web_search as its only tool and tool_choice="required", at most twice: turn 1 for all metrics, and one retry turn only if some metric is retry-eligible. It hardcodes its own budget (1 search + 1 retry per metric). Every call is tagged with a metric_label. The LLM produces every call, including retries; the app owns attempts — it decides whether a retry turn happens and which metrics may be retried. The guard (R3.M1.1) only admits or rejects. A shared helper for the raw assistant ↔ tool-call ↔ tool-result cycle absorbs the boilerplate it shares with phase 2.

Prerequisite — provider failure class on LLMProviderError (C3.1.2 change, NOT DONE; the cause rule and the breaker depend on it)
What is wrong today. LLMProviderError carries only a message. call_turn (llm_provider.py, provider loop) logs each provider's failure and moves to the next provider, keeping nothing about the kind of failure. When the chain runs out, the raised MetricResolutionProviderError carries stage only, so phase 1 cannot tell an outage (timeout, 5xx) from a content failure (refusal) and cannot set cause.
Change. At each place a provider raises LLMProviderError, set a failure_class on it, because that code already knows what went wrong:
availability: timeout, 5xx, connection error, or a 429 after its retries ran out.
content: a refusal, an abnormal finish_reason, or the defensive-parse anomaly. call_turn and call_structured collect one failure_class per failed provider. When the chain is exhausted they raise MetricResolutionProviderError with cause = availability if every collected class is availability, and cause = content if any is content (the Error cause rule below). circuit_open is never set by a provider; only the caller-side breaker check raises it.
Why. The run-level breaker (R3.M1.5) counts only cause = availability. Without failure_class, no failure can be labelled availability, the counter never moves, and the breaker can never trip during an outage.
Scope. call_turn and call_structured are shared by discovery (R3.M1.3), phase 1, triage, phase 2 and resolution (R3.M2.2), so all of them get cause. cause is set only when provider_error_cls is MetricResolutionProviderError; R1's error class and behavior are unchanged.
Tests to add. Fake providers failing with: all timeouts / 5xx → availability; one refusal plus one timeout → content; all refusals → content. Existing R1 provider-chain tests pass unchanged.
Traceflow
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

Decisions — Generally mandatory
Termination. Phase 1 has at most two search turns. After turn 1, if no metric is retry-eligible, the phase ends without another LLM call; otherwise one retry turn runs, and the phase then ends because every retried metric's budget is spent. Before a call reaches the gateway, the loop checks the metric still has an attempt; a call with none left is not executed. A metric's budget is spent when its search terminates cleanly — ok or empty (R3.M1.2) — or its one retry is used. Only a failed outcome, a timeout, or a guard rejection is retry-eligible; empty is terminal and never retried. An ok or empty metric is never searched again.
Two retry layers. Gateway-internal retries (the per-kind gateway retry limits prerequisite above) do not count against the metric's budget; the budget retry applies only after the gateway has returned a typed failed, and also covers guard rejections the gateway never sees.
Concurrency. Tool calls in one turn run together with gather under the Parallel gateway semaphore, async-native on the event loop (C3.1.1); results are appended in tool_call_id order.
Failure handling (D5).
Tool-call failure (phase 1). Every call is shaped by R3.M1.2 into exactly one ok / empty / failed tool message; the loop appends it and continues.
LLM provider-chain failure (phase 1). If call_turn raises MetricResolutionProviderError (turn 1 or the retry turn), phase 1 stops and passes it up. No tool message is appended and no budget retry is used.
Error cause (C3.1.2). MetricResolutionProviderError carries stage and a required cause:
availability: every provider in the chain failed with a timeout, 5xx, connection error, or a 429 after its retries ran out.
content: at least one provider failed with a refusal, an abnormal finish_reason, or the defensive-parse anomaly. A chain with mixed causes is content.
circuit_open: the breaker was open, so no call was made.
Amenity-level outcome. A MetricResolutionProviderError from any LLM step of an amenity pipeline (phase 1, triage, phase 2, resolution) ends that amenity. Its remaining steps are skipped, any evidence gathered is discarded, and every metric is unresolved with reason resolution_call_failed. stage records the failed step and cause records why (on the error and in the pipeline's log line; the record carries only the reason). The run continues with the other amenities.
Discovery is not ended by this rule. A discovery failure (R3.M1.3) keeps its own outcome: none result, and the amenity still runs.
Run-level circuit breaker (owned by R3.M1.5).
Counter. One shared counter per run. It goes up by 1 for each cause = availability failure from an amenity pipeline or a discovery LLM call (tool turn or selection turn), and resets to 0 when any LLM call succeeds. Safe without a lock because everything runs on one event loop (C3.1.1).
Trip. The breaker opens when the counter reaches N (configurable, default 3) and stays open for the rest of the run.
Check point. breaker_open is checked immediately before every call_turn and structured call (phase 1, triage, phase 2, resolution), after the LLM-call permit is acquired, and before each discovery coroutine starts Stage 1.
When open (amenity step). The call isn't made. The step raises MetricResolutionProviderError(stage = <step>, cause = circuit_open), which the amenity-level outcome handles. Phase 1 starts with call_turn, so an amenity that hasn't started yet stops at its first check, before any search or Firecrawl call.
When open (discovery). The work item skips its search and selection turn and gets a none result.
Labelling. Breaker-skipped amenities use reason resolution_call_failed with cause = circuit_open. No new unresolved reason is added, so the record schema doesn't change.
Not counted. content and circuit_open failures never move the counter.
Run-level raise. The run raises MetricResolutionProviderError when no amenity pipeline completed its LLM steps without a provider error (every amenity failed, was breaker-skipped, or a mix). Otherwise it returns records, with the failed and skipped amenities unresolved.
Conversation state. One message list per amenity, provider-neutral (C3.1.2), shared with triage and phase 2 — the loops are separate functions, not separate conversations.
Decisions — Problem-specific nuances
Instruction content. Amenity identity, the resolved website_url (R3.M1.3) when present, and every metric with its fields and resolution_source.web_target — the search direction used for both classes. scrape_target / review_target are not shown in phase 1. The LLM is told to emit one web_search per metric, for all metrics, in the first turn (never split across turns), tag each call with metric_label, and on a retry turn re-emit a call only for the metrics whose tool result failed.
Retry turn — who retries and what the LLM sees. The LLM re-emits the retry; the app never reissues a search call itself. The retry turn replays the full shared history (instruction, the LLM's own turn-1 calls with their metric_label / objective / search_queries, and every tool result), so nothing is re-sent and the turn-1 results stay in place. The LLM matches each failed result to its own call by tool_call_id and may reword the queries.
failed tool message content. States that the call failed, the failure kind in a few words (e.g. timed out), and the metric_label — the loop adds the label from the admitted call, since it is stripped before MCP execution. It carries no retry flag: the app owns the attempt count, and the instruction states the one-retry rule once.
tool_choice = "required" on both turns. Turn 1 and the retry turn both call call_turn with tool_choice="required", matching discovery (R3.M1.3). The retry turn only runs when at least one metric failed, so there is always a call to make; the instruction says which metrics to re-emit; and "required" rules out a reply with no tool_calls at the API level. A "no tool_calls" case is therefore not handled — it cannot occur. ("required" forces at least one call, not one per metric; one call per metric is the instruction's job, and an untagged metric is caught by the coverage rule.)
Host-scoped queries are per metric, keyed off evidence_class. When a website_url is present and the call's metric_label is a factual metric, the instruction asks for at least one host-scoped query alongside broader off-site queries inside the same call's search_queries — never scoping every query to the host (web and scrape stay complementary per D7). For an experiential metric, no host-scoped query is used: the official site is the amenity's own marketing and cannot meet an experiential verification bar, and experiential metrics are never scraped.
Evidence recording. Each hit of an ok web_search result becomes one evidence item:
source_kind = web, url = the hit's url, retrieved_at = the call's retrieved_at, metric_labels = {the call's tagged metric}, evidence_id = a new UUID.
shaped_text = the hit's title + "\n" + its excerpts (joined with newlines) — exactly what the hit carries in the tool message, so R3.M2.4's quote check runs on what the LLM saw.
Two hits in one call with the same (web, url, shaped_text) are one item; the same URL with different shaped_text is a distinct item, never collapsed (see the metrics_source_content shape bullet above).
An empty result has no hits and a failed call has no result, so neither records an item.
Coverage. A metric no phase-1 call was tagged with is set unresolved by the app, whatever triage says.
Incomplete evidence (spent budget). If the phase ends with a metric still failed after its retry (or with its retry not taken), triage runs normally on the evidence that exists. This covers tool-call failures only; an LLM provider-chain failure in either turn ends the amenity and discards the turn-1 evidence (Failure handling above).
Not yet decided (flagged for discussion). The guard works on the whole message, all-or-nothing, so one malformed call (for example a metric_label not in the set) rejects the entire turn and every metric in it loses an attempt, whereas execution failures are per call. (Resolved: who triggers the retry — the LLM re-emits, for failed metrics only; fan-out across metrics — all metrics in turn 1, by instruction; tool_choice — "required" on both turns.)