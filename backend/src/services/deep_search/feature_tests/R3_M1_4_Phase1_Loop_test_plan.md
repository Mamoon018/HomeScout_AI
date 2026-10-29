# R3.M1.4 Step 1 (Phase-1 Loop): Behavior Test Plan

Planned with `skills/test_writing_skills.md` against the implementation described in
`feature_context/R3_M1_4_Phase1_Loop_Implementation_Plan.md` and spec R3.M1.4 step "1. Phase-1 Loop"
(spec lines 596+). Real-run data shapes are taken from `sample_outputs.py` (R3.M1.4 object trace):
multi-line markdown excerpts, ten hits per search, and near-duplicate URLs that differ only by a
trailing `%20`.

Test file: `feature_tests/test_r3_m1_4_phase1_behavior_suite.py`. It complements
`test_r3_m1_4_phase1_loop.py` (the implementation-time suite) and targets the decisions that suite
does not pin down: per-metric billed-search ceiling under hostile LLM output, history replayability,
evidence-text fidelity on real excerpts, per-amenity failure isolation, and exact breaker counting.

**Shared real-vs-mock rule (all entries).** Faked: the LLM provider edge (a routing fake that answers
per amenity from a queue, so concurrent pipelines get deterministic turns) and the MCP gateway's
`search_web` (outcomes keyed by objective). Real: `StructuredLLMCaller` (fallback + `cause`
aggregation), R3.M1.1 catalog, guard and steps 3-5, budget admission, R3.M1.2 shaping, evidence store,
circuit breaker, pipeline catch, STEP 5 sweep, the official-URL gate, and the prompt builder.
`AMENITY_PIPELINE_CONCURRENCY` is set to 1 only in the breaker tests (a config constant, not logic) so
completion order, which the breaker counts in, is deterministic.

---

## Entries

### 1. `test_no_metric_gets_more_than_two_billed_searches_even_when_the_llm_keeps_asking`
- **Target:** `SpecificMetricResolution._phase1_loop` (budget admission inside `_run_phase1_turn`).
- **Core behavior:** the app owns attempts: one search + one retry per metric; `ok`/`empty` are never searched again.
- **Behavior under test:** on the retry turn the LLM re-emits a done (`ok`) metric, a terminal (`empty`) metric, and the failed metric twice; only the first failed-metric call reaches the gateway.
- **Type:** unit (service method, faked edges).
- **Real vs mocked:** shared rule.
- **Evidence:** counts real gateway invocations per metric (each one is billed money, so the count is the behavior); a budget bug shows up as a 3rd call for a metric or any 2nd call for an `ok`/`empty` metric.

### 2. `test_phase1_never_runs_more_than_two_llm_turns_and_needs_a_failure_for_the_second`
- **Target:** `_phase1_loop` retry decision.
- **Core behavior:** at most two turns; turn 2 only when some metric is retry-eligible.
- **Behavior under test:** (a) all metrics `empty` → exactly 1 LLM call; (b) a metric fails twice → exactly 2 LLM calls, metric ends `failed`.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** the provider's recorded call count is the cost boundary; a wrong eligibility rule (empty treated as failed, or looping while failed) changes the count.

### 3. `test_retry_turn_resends_turn_one_history_unchanged_with_the_failure_named`
- **Target:** `_phase1_loop` / `_run_phase1_turn` shared conversation.
- **Core behavior:** the retry turn replays the same history (nothing re-sent, no new user message); the `failed` tool message carries the label and failure kind, no retry flag.
- **Behavior under test:** the messages sent on turn 2 equal the turn-1 messages plus the turn-1 assistant message and its tool messages, and the failed message is `{status, metric_label, failure}`.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** compares what the provider actually received on each turn; extra user messages, a rewritten instruction, or a failed message without its label all fail it.

### 4. `test_history_stays_replayable_through_rejected_skipped_and_out_of_catalog_calls`
- **Target:** `_run_phase1_turn` + R3.M1.1 steps 3-5.
- **Core behavior:** every kept tool call gets exactly one tool message, placed right after its assistant message; out-of-catalog calls are removed before replay.
- **Behavior under test:** turn 1 is guard-rejected (invalid label + out-of-catalog call + valid sibling); turn 2 contains a duplicate and a done metric.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** validates the final message list with the provider's own pairing rule (each assistant message's call ids are answered by the tool messages immediately after it, in any order, and nothing else); a dangling, misplaced, or stray-tool reference fails it.

### 5. `test_two_rejected_turns_end_metrics_failed_without_any_billed_search`
- **Target:** `_attribute_rejected_turn` via `_phase1_loop`.
- **Core behavior:** a guard rejection spends the metric's attempt without touching the gateway; after the retry is spent, phase 1 ends.
- **Behavior under test:** both turns rejected → attributed metrics end `failed`/`rejected` with 2 attempts, 0 gateway calls, 2 LLM calls.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** zero gateway calls proves rejected messages are never executed; attempts == 2 and no third LLM call prove the budget counted the rejections.

### 6. `test_evidence_text_is_exactly_what_the_llm_saw_for_real_multiline_excerpts`
- **Target:** `_shape_web_search` + `_record_web_evidence` + `MetricsSourceContent.record`.
- **Core behavior:** `shaped_text` = hit title + `\n` + hit text, identical to the hit in the tool message (R3.M2.4 checks quotes against it).
- **Behavior under test:** with real excerpt text from the sample run (markdown, blank lines, `...` gaps, unicode €), each recorded item matches the JSON the LLM received, field for field.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** reconstructs the expected text from the parsed tool-message JSON, not from the fixture, so it catches any drift between the two paths (trimming, re-joining, dropped title).

### 7. `test_url_is_part_of_evidence_identity_even_for_near_duplicates`
- **Target:** `MetricsSourceContent.record` through the loop.
- **Core behavior:** identity is `(source_kind, url, shaped_text)`.
- **Behavior under test:** real near-duplicate URLs (`.../opening-hours-and-prices` vs `...%20`) with identical text stay two items; the identical hit found by two metrics is one item with both labels.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** item count and label sets are observable store state; keying on text alone (or URL alone) changes them.

### 8. `test_each_metric_bucket_holds_only_evidence_from_its_own_search`
- **Target:** `MetricsSourceContent.items_for` through the loop.
- **Core behavior:** attribution is per tagged call; empty/failed metrics get no items.
- **Behavior under test:** distinct hits per metric; one metric `empty`, one `failed` after retry.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** compares each bucket's URLs to exactly that metric's hits; mis-attribution or recording for a non-ok call fails it.

### 9. `test_empty_and_failed_stay_distinct_outcomes`
- **Target:** ledger (`MetricSearchOutcome`) via `_phase1_loop`.
- **Core behavior:** `empty` = clean no-evidence (terminal, no failure kind); `failed` keeps the gateway kind (R3.M2 maps them to different reasons).
- **Behavior under test:** one `empty` metric and one metric that times out then is rate-limited.
- **Type:** unit.
- **Real vs mocked:** shared rule.
- **Evidence:** asserts `(status, attempts_used, failure_kind)` triples; collapsing empty into failed (or losing the last kind) changes them.

### 10. `test_tool_failures_never_end_the_amenity`
- **Target:** `run_specific_metric_resolution` (entry).
- **Core behavior:** D5: a tool failure becomes a `failed` tool message; the amenity still completes.
- **Behavior under test:** every search fails in both turns → record `completed`, all metrics `failed`, no evidence, no run-level raise.
- **Type:** e2e (real entry point, faked edges).
- **Real vs mocked:** shared rule.
- **Evidence:** outcome `completed` (not `resolution_call_failed`/`pipeline_error`) is the observable contract.

### 11. `test_retry_turn_provider_failure_discards_only_that_amenitys_evidence`
- **Target:** entry → pipeline catch.
- **Core behavior:** a provider failure in any phase-1 turn ends that amenity, discards its gathered evidence, and leaves siblings untouched.
- **Behavior under test:** amenity A's turn 1 gathers evidence, its retry turn hits a provider refusal; amenity B completes.
- **Type:** e2e.
- **Real vs mocked:** shared rule (routing provider keeps A and B independent of scheduling).
- **Evidence:** A's record has `phase1=None`, `failed_stage=r3_m1_4_phase1_retry`, `failed_cause=content` even though A's turn-1 searches succeeded; B's evidence is intact; the run does not raise.

### 12. `test_availability_outage_opens_breaker_and_later_amenities_make_no_llm_call`
- **Target:** entry + `_CircuitBreaker` + `_counted_llm_call`.
- **Core behavior:** N consecutive availability failures open the breaker; later steps raise `circuit_open` without calling the provider; the run raises when nothing completed.
- **Behavior under test:** threshold 2, 5 amenities, provider always times out, pipelines run one at a time.
- **Type:** e2e.
- **Real vs mocked:** shared rule; concurrency constant set to 1.
- **Evidence:** exactly 2 provider calls (one per amenity before the trip) and causes `[availability, availability, circuit_open x3]` in order; a breaker that never trips, trips late, or still calls the provider fails it.

### 13. `test_content_failures_never_open_the_breaker`
- **Target:** `_CircuitBreaker.record_failure` via entry.
- **Core behavior:** only `availability` counts.
- **Behavior under test:** threshold 2, 3 amenities all refused (content).
- **Type:** e2e.
- **Real vs mocked:** shared rule; concurrency 1.
- **Evidence:** all 3 amenities reach the provider and fail with `content`; the run raises with `content`, not `circuit_open`.

### 14. `test_a_successful_llm_call_resets_the_outage_count`
- **Target:** `_CircuitBreaker.record_success` via entry.
- **Core behavior:** "consecutive" means no success in between.
- **Behavior under test:** threshold 2: fail (availability), succeed, fail (availability).
- **Type:** e2e.
- **Real vs mocked:** shared rule; concurrency 1.
- **Evidence:** the third amenity fails with `availability` (not `circuit_open`) and the run returns normally; without the reset it would trip.

---

## Left out on purpose
- Instruction host-scoping and the identity-merge unit cases: already covered in `test_r3_m1_4_phase1_loop.py`.
- Gateway retry waits and `cause` aggregation: covered in the C3.1.1 / C3.1.2 suites.
- Log line contents: not behavior a consumer relies on.

## Verification: each test fails for the right reason

Each bug below was injected at runtime by a scratch pytest plugin (monkeypatch only; no source file
was edited), and the suite was run against it. The clean suite passes (15/15).

| Injected bug | Caught by |
| --- | --- |
| budget check disabled (`_refusal_reason` always allows) | 1 |
| retry turn always runs (`_retry_eligible` returns every metric) | 2 (all_empty), 6, 7, 11, 14 |
| retry turn appends a new user message | 3 |
| `failed` tool message drops `metric_label` | 3 |
| out-of-catalog calls kept in the replayed message | 4 |
| guard rejections spend no attempt | 4, 5 |
| `shaped_text` drops the title | 6 |
| evidence identity ignores the URL | 7 |
| every hit attributed to the first ok metric | 7, 8 |
| `empty` shaped as `failed` | 1, 2, 6, 7, 9 |
| a tool failure raises instead of being shaped | 1, 2, 3, 8, 9, 10, 11 |
| retry-turn provider error swallowed (evidence kept) | 11 |
| breaker never trips | 12 |
| breaker counts `content` failures | 13 |
| breaker never resets on success | 14 |

Two entries were strengthened after the first mutation pass exposed gaps: entry 8 now has two `ok`
metrics in one turn (single-metric attribution bugs were invisible), and entry 14 now has a fourth
amenity (the reset only shows on the call after the second failure).

## To-do
- [x] Write the tests from each entry above
- [x] Run them and verify each fails for the right reason (break the behavior; confirm the test catches it), using runtime monkeypatch mutations from a scratch pytest plugin, so no source file is edited
