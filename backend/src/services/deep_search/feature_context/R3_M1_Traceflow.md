# R3.M1 — Detailed Traceflow (Evidence Acquisition)

## Context

**Why this document exists.** We are implementing **R3.M1 (Evidence Acquisition)** of the
*Specific Metric Resolution* responsibility. The spec
([R3_Specific_Metric_Resolution_spec.md](R3_Specific_Metric_Resolution_spec.md))
describes each sub-component (C3.1.1, C3.1.2, R3.M1.1–R3.M1.5) in isolation, and R3.M1.5 carries a
*high-level* trace of `run_specific_metric_resolution`. What it does **not** show is how the seven
pieces actually interlock at runtime — how a single work item flows from "we have a place_id" to
"we have a `metrics_source_content` store ready for resolution," and how the same
catalog→turn→guard→execute→shape cycle is reused by discovery, phase 1, and phase 2.

**Goal.** Surface the existing R3.M1.5 trace as-is, then expand it into one complete box-and-arrow
traceflow that makes the whole M1 mechanism legible: the orchestration spine, the reusable tool-turn
atom, and the per-amenity pipeline. R3.M2 (resolution) is shown only as the downstream hand-off
endpoints, since the current focus is M1.

> This is a **traceflow/understanding artifact**, derived entirely from the finalized decisions in
> the spec. It documents behavior; it does not change it.

---

## Part 1 — The existing R3.M1.5 trace (surfaced as-is)

This is the trace the spec already carries for `run_specific_metric_resolution`
([R3_Specific_Metric_Resolution_spec.md](R3_Specific_Metric_Resolution_spec.md), R3.M1.5 "Trace flow").
It is the **orchestration spine** — correct but coarse: STEP 3 (discovery) and STEP 4 (pipelines)
are each one line that hides the entire M1.1/M1.2/M1.3/M1.4 machinery.

```
run_specific_metric_resolution(state)                         [R3.M1.5, method on SpecificMetricResolution]
│
├─ open gateway sessions (Parallel + Firecrawl)          [C3.1.1 — session scope = method]
│
├─ STEP 1  Build plan_index  (category_id → CategoryMetricPlan)      ── once
│
├─ STEP 2  Derive work items  = eligible (category_id, place_id)      [RC7]
│          from state.discovered_places × categories with ≥1 specific_metrics
│
├─ STEP 3  DISCOVERY BATCH  (R3.M1.3)                      ── concurrent, own hard barrier
│          Stage-0 sync pre-pass (all wi) → await asyncio.gather over declined subset [discovery_sem]
│          each task: breaker_open → none · LLM ProviderError → none (availability → counter +1)
│          → website_search_results[(cat,place)] = {website_url|None, origin}
│          ╌╌╌ barrier: ALL verdicts ready before any pipeline starts (RC8) ╌╌╌
│
├─ STEP 4  AMENITY PIPELINES  (R3.M1.4 + R3.M2.2–R3.M2.4)    ── concurrent, under bounds
│          results = await asyncio.gather(*tasks, return_exceptions=True)
│          each pipeline: phase1_loop → triage → (cond.) phase2_loop → R3.M2.2–2.4
│          every LLM call: breaker check first · ProviderError → amenity ends, all unresolved
│          ╌╌╌ HARD BARRIER: gather returns only when ALL N pipelines finished ╌╌╌
│
├─ STEP 5  Post-gather sweep (Exception → synthesize all-unresolved record)  [D5]
│          run-level raise: no pipeline finished its LLM steps without a ProviderError
│
├─ STEP 6  R3.M2.5  COMBINE  → state.amenity_records = AmenityMetricsSet(1.0)
│
└─ close gateway sessions (aclose)                         [C3.1.1]
```

**What it leaves implicit (and what Part 2/3 expands):**

- STEP 3 "DISCOVERY BATCH" = per work item, a full **catalog → tool-turn → guard → execute → shape
  → structured-selection** sequence (R3.M1.1 + C3.1.2 + C3.1.1 + R3.M1.2).
- STEP 4 "each pipeline" = `phase1_loop → triage → phase2_loop`, each of which **reuses the same
  tool-turn cycle** with a different context, budget, and tool set.
- The `raw_tool_definitions` that C3.1.1's `open()` retrieves and how they reach R3.M1.1.
- Where `metrics_source_content` (the normalized evidence set) is written, and how dedup + record
  happens in phase 2.
- How `evidence_class` decides which unresolved metrics phase 2 may scrape (factual only).

---

## Part 2 — The reusable tool-turn cycle (the M1 "atom")

Discovery, phase 1, and phase 2 all drive the LLM through the **same** five-stage cycle. Only the
`context`, the exposed tools, the app-injected arguments, and the budget differ. Understanding this
atom once makes the rest of the traceflow collapse into "the atom, three times."

```
┌─ REUSABLE TOOL-TURN CYCLE ───────────────────────────────── used by: discovery · phase1 · phase2 ─┐
│                                                                                                    │
│   in: context, raw_tool_definitions (from C3.1.1 open → workflow state), messages, validation_ctx │
│        │                                                                                           │
│        ▼                                                                                           │
│  ① [R3.M1.1 · Step 1]  BUILD LLM-FACING CATALOG                                                    │
│        select server+tool by context policy → derive restricted schema (explicit allowlist,        │
│        preserve $ref/$defs, drop app-controlled fields) → adapt to function-tool format            │
│        out: tool_catalog : list[dict]        (fail BEFORE any LLM call if server/tool/schema bad)  │
│        │                                                                                           │
│        ▼                                                                                           │
│  ② [C3.1.2]  call_turn(messages, tools=tool_catalog, tool_choice)                                  │
│        BREAKER CHECK first (after LLM permit): open → ProviderError(cause=circuit_open), no call   │
│        OpenAI → Groq chain (same LLM_PROVIDER_ORDER). tools-only; NO response_format.              │
│        out: assistant message + optional tool_calls                                                │
│        chain exhausted → MetricResolutionProviderError(stage, cause = availability | content)      │
│          → cycle STOPS: no tool message, no budget retry; error passed up to the caller            │
│            (discovery → none · amenity pipeline → amenity ends, see R3.M1.5 catch)                 │
│        │                                                                                           │
│        ▼                                                                                           │
│  ③ [R3.M1.1 · Step 2]  GUARD PROPOSED CALLS   (whole-message, all-or-nothing)                      │
│        no calls → no_tool_calls · outer fields + unique ids → invalid_call_structure               │
│        name ∈ catalog? no → out_of_catalog · decode arg JSON → schema validate → in_catalog        │
│        additional validator (metric_label ∈ metric set; scrape id ∈ issued set) via validation_ctx │
│        phase-2 scrape: every metric_label ∈ phase-2-eligible set (unresolved + factual)            │
│        │                                                                                           │
│        ├── REJECTED ─→ [Step 3] build rejection outcomes                                           │
│        │               [Step 4] sanitize replay history:                                          │
│        │                   in_catalog     → keep assistant call + paired error in history          │
│        │                   out_of_catalog → strip the call + its response before replay (Groq)     │
│        │               (retry eligibility is the LOOP's decision — R3.M1.4, not the guard)         │
│        │                                                                                           │
│        └── ACCEPTED ─→ [Step 5] prepare admitted calls:                                            │
│                            inject app-controlled args (map/scrape url, formats),                   │
│                            strip metric_label before MCP execution                                 │
│        │                                                                                           │
│        ▼                                                                                           │
│  ④ [C3.1.1]  GATEWAY EXECUTE   calls in one turn run together via gather                           │
│        per-server semaphore (Parallel=4 / Firecrawl=2) + per-call timeout + per-kind gateway retry:│
│        Firecrawl ALSO paced by token bucket ≤10/min. is_error / dropped-SSE / 429 → typed outcome. │
│        timeout/transport → 1 retry (2 s) · rate limit → 30 s, 30 s · budget retry covers the rest. │
│        │                                                                                           │
│        ▼                                                                                           │
│  ⑤ [R3.M1.2]  SHAPE RESULT  → exactly ONE `tool` message per call                                  │
│        ordered guard: terminated cleanly? NO → failed                                              │
│                                            YES → has content? → ok(result) : empty                 │
│        (failed = retry-eligible · empty = TERMINAL, never retried · result always passed through)  │
│        │                                                                                           │
│        ▼                                                                                           │
│   append `tool` message to the amenity conversation (tool_call_id order)                           │
│   + record evidence item in metrics_source_content (source_kind,url,shaped_text; metric_labels)    │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Context parameterization of the atom:**

| Phase / step | `context` | Exposed tool(s) | LLM sets | App injects | Budget (per R3.M1.4 / R3.M1.1) |
|---|---|---|---|---|---|
| Discovery (R3.M1.3) | `website_discovery` | `web_search` | `objective`, `search_queries` | — | 1 call (+1 retry of selection turn only) |
| Phase 1 (R3.M1.4) | `metric_web_search` | `web_search` | `objective`, `search_queries`, `metric_label` (any metric, both classes; direction from `web_target`) | — | 1 search + 1 retry **per metric** |
| Phase 2 map (R3.M1.4) | `site_map` | `firecrawl_map` | *(nothing)* | homepage `url` | 1 map (+1 retry) |
| Phase 2 scrape (R3.M1.4) | `metric_scrape` | `firecrawl_scrape` | candidate `id`, `metric_label`(s) ∈ **phase-2-eligible set** (unresolved + `factual`; hint from `scrape_target`) | real `url`, `formats` | 1 scrape/eligible metric, dedup→≤8 distinct, +1 retry each |

**Two retry layers (prerequisite: per-kind gateway retry limits).** A failed call can be retried at two layers, each owning different failure kinds. The gateway's retry limit is read from the **failed kind's own backoff tuple** (not one shared value), so timeout/transport can be shortened without touching rate limits:

| Failure | Retried where | Cost |
|---|---|---|
| Timeout | Gateway, **1** retry after 2 s → then budget layer | no LLM turn |
| Dropped connection / transport error | Gateway, **1** quick retry (2 s) | no LLM turn |
| Rate limit (429) | Gateway wait 30 s, then 30 s (`Retry-After` overrides) | no LLM turn |
| Guard rejection | Budget layer only (gateway never sees it) | one LLM turn |
| Anything still `failed` after the gateway | Budget layer: 1 retry per metric (full cycle ①–⑤ again) | one LLM turn |

Gateway-internal retries do **not** consume a metric's budget. Worst-case hold-up for a timing-out call drops from ~95 s (30+2+30+3+30) to ~62 s (30+2+30).

**LLM provider-chain failure is a third, separate layer (not a retry).** The two layers above cover *tool* calls. When the LLM call itself (② `call_turn`, or a structured call) exhausts the provider chain, it raises `MetricResolutionProviderError` with `stage` and `cause`:

| `cause` | When | Breaker counter |
|---|---|---|
| `availability` | **every** provider failed with timeout / 5xx / connection error / 429 after retries | +1 |
| `content` | ≥1 provider failed with refusal / abnormal `finish_reason` / defensive-parse anomaly (mixed → `content`) | unchanged |
| `circuit_open` | breaker was open, no call made | unchanged |

Any successful LLM call resets the counter to 0. At `N` (default 3) the breaker opens for the rest of the run. Outcome by caller: discovery → `none`, amenity still runs; amenity pipeline step (phase 1, triage, phase 2, resolution) → amenity ends, evidence discarded, every metric `unresolved(resolution_call_failed)`.

**Phase-2 eligibility** is derived by the app from `evidence_class` (never parsed from text): only metrics that are `unresolved` after triage **and** `factual` (they carry a `scrape_target`) can be scraped. An unresolved `experiential` metric skips phase 2 and reaches R3.M2 with its web evidence, where the Google-reviews block — read via its `review_target` hint — is the fallback.

---

## Part 3 — Complete detailed R3.M1 traceflow

The spine from Part 1, with STEP 3 and STEP 4 fully expanded into the atom from Part 2.

```
════════════════════════════════════════════════════════════════════════════════════════════════
  run_specific_metric_resolution(state)                       [R3.M1.5 · SpecificMetricResolution]
════════════════════════════════════════════════════════════════════════════════════════════════

┌─ OPEN  [C3.1.1] ──────────────────────────────────────────────────────────────────────────────┐
│  open Parallel + Firecrawl sessions (one Client/server, this async task = session scope)        │
│  handshake → tools/list CAPABILITY CHECK:                                                        │
│      Parallel : web_search(objective, search_queries)                                           │
│      Firecrawl: firecrawl_map(url) + firecrawl_scrape(url, formats)   (crawl retained, UNchecked)│
│      miss → McpToolUnavailableError  (raises BEFORE any amenity work)                            │
│  retrieve raw MCP tool defs → store in workflow state as `raw_tool_definitions`                 │
│      (keyed server → tool; read later by every R3.M1.1 catalog build)                           │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
┌─ STEP 1 ────────────────────────────────────────────────────────────────────────────────────┐│
│  build plan_index : category_id → CategoryMetricPlan                              ── once      ││
└───────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                                                 │
┌─ STEP 2  (RC7 eligibility) ───────────────────────────────────────────────────────────────────┐
│  work_items = [ (category_id, place_id, taxonomy_node, depth, specific_metrics) … ]   (N items) │
│    source: state.discovered_places  ×  categories whose CategoryMetricPlan has ≥1 specific_metric│
│    (basic_profile category with no specific_metrics → NO work item)                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
┌─ STEP 3   DISCOVERY BATCH   [R3.M1.3]   Stage-0 sync pre-pass → fan out declined only · HARD BARRIER ┐
│                                                                                                 │
│  SYNC PRE-PASS (all work items · no task / no sem / no I/O):                                     │
│    rec = state.predefined_records[cat][place]                                                   │
│    official_url_gate(rec.website, rec.name):                                                    │
│      OFFICIAL  → website_search_results[key] = {website_url=rec.website, origin=google}  (done)  │
│      otherwise → declined += wi            (gate error → declined, NEVER none)                   │
│    → store state.official_gate_results[key] for EVERY wi (telemetry; both verdicts)             │
│      {name, website, host, registered_domain, sld, suffix, compact_name, compact_sld,           │
│       verdict, reason_code}  — separate from website_search_results                             │
│                                                                                                 │
│  tasks = [ discover_search(wi) for wi in declined ]   ;   await asyncio.gather(*tasks)           │
│  (barrier waits on declined subset only; pass-items already in dict → RC8 holds for all N)       │
│                                                                                                 │
│  ┌─ discover_search(wi) ── Stage 1 only; gate already applied in pre-pass ───────────────────┐  │
│  │  BREAKER CHECK: breaker_open → none (skip search + selection turn)                         │  │
│  │  READ INPUTS: rec.name + rec.address (full, verbatim) → LLM                                │  │
│  │  ╭─ TOOL-TURN CYCLE (atom), context = website_discovery ──────────────────────────────╮   │  │
│  │  │  ① build catalog (parallel/web_search; objective+search_queries)                    │   │  │
│  │  │  ② call_turn → LLM builds query; told to use postal code (in address)               │   │  │
│  │  │  ③ guard → ④ gateway web_search (Parallel sem) → ⑤ shape (ok/empty/failed)           │   │  │
│  │  ╰──────────────────────────────────────────────────────────────────────────────────╯   │  │
│  │  ↓ WebSearchResult.excerpts (url + title + snippet)                                        │  │
│  │  CANDIDATE INDEXING (app): drop url=None · ids c1..cN · candidates(id,url,title,text)       │  │
│  │     + id→url map   (opt: store state.discovery_search_results)                             │  │
│  │  STRUCTURED SELECTION TURN  [C3.1.2 call_structured · no tools]                             │  │
│  │     LLM returns { selected_id } OR { selected_id: null }  — NEVER a URL                     │  │
│  │  VERDICT VALIDATOR + RESOLVE  (R3.M1.3 body check — NOT the R3.M1.1 tool-call guard):       │  │
│  │     null → none · id∉map → invalid → 1 retry then none · id∈map → url=map[id] (discovered)  │  │
│  │     tool failed → 1 retry then none                                                         │  │
│  │  LLM ProviderError (tool turn or selection) → none, amenity still runs                     │  │
│  │     cause = availability → breaker counter +1 · LLM success → counter = 0                  │  │
│  └────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                 │
│  → website_search_results[(cat,place)] = { website_url | None , website_origin }   (all N)       │
│    (declined task exception / timeout → none)                                                   │
│  ╌╌╌╌╌ BARRIER: every work item has a verdict before ANY pipeline starts (RC8: URL first) ╌╌╌╌╌  │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
┌─ STEP 4   AMENITY PIPELINES   concurrent · under bounds · gather(return_exceptions=True) ───────┐
│  tasks = [ pipeline(wi, website_search_results[key]) for wi in work_items ]                     │
│                                                                                                 │
│ ┌─ pipeline(wi) ── one conversation + one metrics_source_content · writes NO shared state ─────┐│
│ │                                                                                              ││
│ │  ╔═ PHASE 1 LOOP ═ [R3.M1.4] ════ turn 1: ALL metrics → ≤1 retry turn (failed only) ═══════╗ ││
│ │  ║ instruction: amenity identity + website_url(if any) + every metric                      ║ ││
│ │  ║   (label, question, value_type, unit, enum_values, evidence_class, verification,        ║ ││
│ │  ║    resolution_source.web_target) — web_target drives search for BOTH classes;           ║ ││
│ │  ║    scrape_target / review_target are NOT shown in phase 1                               ║ ││
│ │  ║   turn 1: ONE web_search per metric, ALL metrics in this turn, each tagged              ║ ││
│ │  ║     with metric_label · retry turn: re-emit ONLY for metrics whose result failed        ║ ││
│ │  ║   both turns: call_turn tool_choice="required" → every reply has ≥1 tool call           ║ ││
│ │  ║   if website_url present AND metric is factual: ≥1 host-scoped query ALONGSIDE          ║ ││
│ │  ║     off-site queries (D7); experiential metric → NO host-scoped query                   ║ ││
│ │  ║                                                                                         ║ ││
│ │  ║   TURN 1 (all metrics):                                                                 ║ ││
│ │  ║     ╭─ TOOL-TURN CYCLE (atom), context = metric_web_search ───────────────────────────╮ ║ ││
│ │  ║     │ ① catalog(web_search;+metric_label) ② call_turn(required) ③ guard(label ∈ set)  │ ║ ││
│ │  ║     │ ② breaker check first · ProviderError → phase 1 STOPS, passes it up             │ ║ ││
│ │  ║     │   (no tool message appended · no budget retry used)                             │ ║ ││
│ │  ║     │ LOOP budget check BEFORE execute: metric with no attempt left → not executed    │ ║ ││
│ │  ║     │ ④ gateway web_search ×calls via gather (Parallel sem)  ⑤ shape ok/empty/failed  │ ║ ││
│ │  ║     ╰─────────────────────────────────────────────────────────────────────────────────╯ ║ ││
│ │  ║     append tool msgs (failed msg = "failed" + kind + metric_label · no retry flag)      ║ ││
│ │  ║     → record web evidence items (ok results only), one per HIT:                         ║ ││
│ │  ║       source_kind=web · url=hit url · shaped_text = title + "\n" + excerpts             ║ ││
│ │  ║       retrieved_at = call's · metric_labels = {the tagged metric} · evidence_id = UUID  ║ ││
│ │  ║       (same triple in one call → one item; same url + different shaped_text → distinct) ║ ││
│ │  ║                                                                                         ║ ││
│ │  ║   APP CHECK: any metric retry-eligible? (failed or guard-rejected, retry unused)        ║ ││
│ │  ║     NO  → phase 1 ends, NO further LLM call → triage                                    ║ ││
│ │  ║     YES → RETRY TURN (same atom · same shared history · nothing re-sent)                ║ ││
│ │  ║           same breaker check + ProviderError rule as turn 1 (stop, pass up)             ║ ││
│ │  ║           LLM matches failed results by tool_call_id, re-emits ONLY those (may reword)  ║ ││
│ │  ║           each retried result is final (ok/empty/failed) → phase 1 ends → triage        ║ ││
│ │  ║                                                                                         ║ ││
│ │  ║   ok / empty metric = done, never re-searched · empty = TERMINAL (burns budget)         ║ ││
│ │  ║   (gateway's own 1-retry for timeout/transport does NOT use this budget)                ║ ││
│ │  ╚═════════════════════════════════════════════════════════════════════════════════════════╝ ││
│ │                              │ (same shared message list)                                    ││
│ │                              ▼                                                               ││
│ │  ╔═ TRIAGE ═ [R3.M1.4] ══ separate STRICT-schema NO-tools request [C3.1.2 call_structured] ╗ ││
│ │  ║   returns {metric_label, status ∈ sufficient|unresolved} per metric (BOTH classes)      ║ ││
│ │  ║   label-set checked · schema/invalid → retry up to 2× · still bad → ALL unresolved      ║ ││
│ │  ║   breaker check first · ProviderError → NOT retried, passed up (amenity ends)           ║ ││
│ │  ║   coverage: metric no phase-1 call was tagged with → unresolved (app-set, ignores LLM)  ║ ││
│ │  ║   evidence all-empty OR all-failed → unresolved  (empty/failed distinction kept for M2) ║ ││
│ │  ╚═════════════════════════════════════════════════════════════════════════════════════════╝ ││
│ │                              │                                                               ││
│ │                              ▼                                                               ││
│ │  PHASE-2 ELIGIBILITY  (app-derived from evidence_class — never parsed from text)             ││
│ │    eligible = { m : triage(m) = unresolved  AND  m.evidence_class = factual }                ││
│ │               (factual ⇔ carries a scrape_target)                                            ││
│ │    unresolved EXPERIENTIAL → not eligible → stays on its web evidence → R3.M2,               ││
│ │               where the Google-reviews block (read via review_target) is the fallback        ││
│ │                              │                                                               ││
│ │            ┌─────────────────┴─ phase-2 gate ─────────────────┐                              ││
│ │      eligible ≠ ∅  AND  website_url ≠ None ?                                                 ││
│ │            │ NO → SKIP phase 2 (all sufficient · all unresolved are experiential · no URL)   ││
│ │            │ YES                                                                             ││
│ │            ▼                                                                                 ││
│ │  ╔═ PHASE 2 LOOP ═ [R3.M1.4] ═ map → select → scrape  (D1, uniform tool loop, not a crawl) ╗ ││
│ │  ║ instruction: the ELIGIBLE metrics + their resolution_source.scrape_target hints         ║ ││
│ │  ║                                                                                         ║ ││
│ │  ║  (a) MAP — first phase-2 call is firecrawl_map                                          ║ ││
│ │  ║      ╭─ atom, context = site_map · app injects url = official homepage ──────────────╮  ║ ││
│ │  ║      │ ① catalog(firecrawl_map; no LLM args)  ② call_turn  ③ guard  ④ gateway        │  ║ ││
│ │  ║      │ ⑤ shape → link set   (Firecrawl sem + ≤10/min token bucket)                   │  ║ ││
│ │  ║      ╰───────────────────────────────────────────────────────────────────────────────╯  ║ ││
│ │  ║      app shapes links → (id,url) CANDIDATE LIST, ≤50, opaque ids fresh per map          ║ ││
│ │  ║      map failed/timeout → 1 retry → GIVE UP phase 2 (metrics stay on web evidence)      ║ ││
│ │  ║                                                                                         ║ ││
│ │  ║  (b) SELECTION TURN — LLM emits firecrawl_scrape calls, ONE page per ELIGIBLE metric    ║ ││
│ │  ║      each call: id (NEVER url) + required metric_label(s) (≥1, list allowed)            ║ ││
│ │  ║      guard: id ∈ issued set? · ≥1 metric_label? (untagged → reject, no orphan)          ║ ││
│ │  ║             every metric_label ∈ eligible set (validation_ctx)? experiential or         ║ ││
│ │  ║             already-sufficient label → reject                                           ║ ││
│ │  ║      selection invalid → 1 retry → still invalid → empty selection → web-only           ║ ││
│ │  ║                                                                                         ║ ││
│ │  ║  (c) DEDUP + RECORD CYCLE  — the one place page↔metric many-to-many is resolved         ║ ││
│ │  ║      1 collect (metric_label, id) requests                                              ║ ││
│ │  ║      2 resolve id → real url via candidate list                                         ║ ││
│ │  ║      3 dedup by url → one firecrawl_scrape per unique url (union of its metrics)        ║ ││
│ │  ║      4 ceiling: >8 distinct urls → drop surplus (those metrics stay on web evidence)    ║ ││
│ │  ║      5 FETCH ONCE — ≤8 scrapes concurrent (Firecrawl sem); app substitutes real url,    ║ ││
│ │  ║        strips metric_label → ④ gateway → ⑤ shape; ok/empty/failed + 1 retry per url     ║ ││
│ │  ║        scrape failed/timeout → 1 retry → still failed → skip page (amenity survives)    ║ ││
│ │  ║        scrape empty → appended, loop continues, NOT retried, NOT a skip, no item        ║ ││
│ │  ║      6 RECORD after results — ONE evidence item (source_kind=scrape) carrying the       ║ ││
│ │  ║        union of requesting metrics in metric_labels (stored once, no duplication)       ║ ││
│ │  ║  no second triage · successful phase 2 not repeated                                     ║ ││
│ │  ║  every call_turn: breaker check first · ProviderError → phase 2 STOPS, passed up        ║ ││
│ │  ╚═════════════════════════════════════════════════════════════════════════════════════════╝ ││
│ │                              │                                                               ││
│ │                              ▼  returns: conversation + metrics_source_content               ││
│ │  ┌─ HAND-OFF TO R3.M2 (per amenity; M1 focus ends here) ───────────────────────────────────┐ ││
│ │  │ metrics_source_content = normalized evidence set of items                               │ ││
│ │  │   {evidence_id, source_kind, url, shaped_text, retrieved_at, metric_labels}             │ ││
│ │  │   identity = (source_kind, url, shaped_text) · identical triple → stored once           │ ││
│ │  │   + amenity-level google_reviews item (metric_labels empty, no metric)                  │ ││
│ │  │ R3.M2.2 resolution turn: per-metric bucket = items whose metric_labels ∋ label          │ ││
│ │  │   + reviews block (reviews eligible only for experiential metrics, via review_target)   │ ││
│ │  │   reads buckets, NOT the thread; strict schema, no tools                                │ ││
│ │  │   → R3.M2.3 conform + verification gate → R3.M2.4 provenance (quote ∈ bucket)           │ ││
│ │  │   → SpecificMetricsRecord                                                               │ ││
│ │  └─────────────────────────────────────────────────────────────────────────────────────────┘ ││
│ │                                                                                              ││
│ │  try:    return SpecificMetricsRecord(resolved/unresolved metrics)                           ││
│ │  except MetricResolutionProviderError (any LLM step: phase 1 · triage · phase 2 · resolution)││
│ │          remaining steps skipped · evidence discarded                                        ││
│ │          return SpecificMetricsRecord(all unresolved(resolution_call_failed))                ││
│ │          log stage + cause (not on the record) · availability → breaker counter +1           ││
│ │  except: return SpecificMetricsRecord(all metrics unresolved)   [D5 — failure isolated here] ││
│ └──────────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                 │
│  ╌╌╌╌╌ HARD BARRIER: gather returns only when ALL N pipelines finished (a failure still         │
│         "finished" — it returned a record). return_exceptions=True → unexpected raise comes     │
│         back as a value, not a cancel of siblings ╌╌╌╌╌                                         │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
┌─ STEP 5  POST-GATHER SWEEP (single-threaded, after barrier) ────────────────────────────────────┐
│  for r in results:  isinstance(r, Exception) → synthesize all-unresolved record [D5 safety net]  │
│                     else → r is a SpecificMetricsRecord                                          │
│  RUN-LEVEL RAISE: no pipeline finished its LLM steps without a ProviderError                     │
│                   (all failed / breaker-skipped / mix) → raise MetricResolutionProviderError     │
│                   N = 0 work items → no raise                                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
┌─ STEP 6  R3.M2.5  COMBINE (run-level, once) ────────────────────────────────────────────────────┐
│  state.specific_records[cat][place] = record                                                     │
│  pair with state.predefined_records → AmenityMetricsRecord → AmenityMetricsSet(1.0)              │
│  → state.amenity_records        (N = 0 → set still built, every specific = None)                 │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
└─ CLOSE  [C3.1.1] aclose() Parallel + Firecrawl sessions ────────────────────────────────────────┘
```

---

## Part 3a — R3.M1.3 Google-URL officiality gate (STEP 3 detail)

`official_url_gate(website, name)` runs **before** any discovery search (STEP 3, once per work item)
and decides whether Google's `PredefinedMetricsRecord.website` can be trusted without searching. It is
cheap, deterministic, and **`tldextract`-based**. **Core idea:** match the brand against the **SLD
label only** (the label left of the public suffix), ignoring subdomain and suffix — so the expensive
direction is decided *by rule*: `brand.evil.com` → DISCOVERY (SLD `evil`), while
`clinic.reseller.greenvalleydental.co.uk` → OFFICIAL (SLD `greenvalleydental`).

```
┌─ OFFICIAL-URL GATE  [R3.M1.3] ─ official_url_gate(website, name) ─────────────────────────────┐
│  0 PRESENCE   website empty / whitespace                                         → DISCOVERY    │
│  1 HOST       urlsplit(website).netloc → lower · strip userinfo/port · rstrip('.')              │
│  2 EXTRACT    sub, sld, suffix = extractor(host)                                                │
│               no sld or no suffix (IP, localhost, bare host)                     → DISCOVERY    │
│               registered_domain = f"{sld}.{suffix}"                                             │
│  3 DENYLIST   registered_domain ∈ DENYLIST  (exact set membership)              → DISCOVERY    │
│               (fast reject only; step 4 already rejects foreign SLDs by rule)                   │
│  4 SLD MATCH  match(compact(name), compact(sld))                                → OFFICIAL      │
│               (website_url = website · origin = google · skip search)                           │
│  5 ELSE                                                                          → DISCOVERY    │
│                                                                                                │
│  compact(x)   = NFKD → drop combining marks → casefold → keep [a-z0-9]   "Café México"→cafemexico │
│  match(cn,cs) = len≥5 both  AND  (cn in cs  OR  cs in cn)                                        │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Library config (locked).** One module-level `TLDExtract(cache_dir=<vendored snapshot>,
suffix_list_urls=[])` — **pinned, offline PSL**, never fetched at runtime (deterministic; refresh is a
maintenance task). **`include_psl_private_domains=True`** — brand-owned platform subdomains
(`brand.wixsite.com`, `brand.github.io`) resolve to the brand's own SLD → OFFICIAL, while foreign apex
domains (`brand.evil.com` → SLD `evil`) are still rejected. (`tldextract==<pin>` + PSL refresh are
noted as a prerequisite in the spec.)

- **Strict by asymmetry.** A false OFFICIAL skips discovery and feeds a wrong site to the crawl
  (expensive, uncorrectable); a false DISCOVERY is cheap and usually re-finds the URL. The SLD rule is
  precise on the OFFICIAL direction; anything ambiguous → DISCOVERY.
- **Denylist is fast-reject only.** Exact membership on `registered_domain` — no longer load-bearing
  for correctness (step 4 rejects foreign SLDs regardless), just skips the name check for known hosts.
- **Accepted residual risk.** A non-denylisted registrable domain whose **SLD itself** matches the
  brand but isn't theirs (a deliberate decoy) → false OFFICIAL; no no-fetch gate catches it, far rarer
  than a label-based gate's leak. Creative-domain / acronym false-negatives fall to DISCOVERY (LLM backstop).

---

## Part 4 — Component interaction legend

**Who owns what, and the dependency edges the traceflow walks** (matches the spec's Dependency order,
[R3_Specific_Metric_Resolution_spec.md:68](R3_Specific_Metric_Resolution_spec.md)):

```
 C3.1.1  MCP gateway ───────────► provides raw_tool_definitions ──► R3.M1.1 (catalog)
   │  open/close, capability check, execute, parse, retry, semaphores, token bucket
   │                                        ▲
   │                                        │ ④ execute admitted calls
 C3.1.2  shared caller ──────────► ② call_turn (tools) · call_structured (schema) · OpenAI→Groq
   │
 R3.M1.1 catalog + guard ───────► ①③⑤-prep: shapes what the LLM may call, admits what it did
 R3.M1.2 result shaper ─────────► ⑤: every call → one ok/empty/failed tool message
 R3.M1.3 URL resolution ────────► STEP 3: website_search_results (atom + structured selection)
 R3.M1.4 phase loop + triage ───► STEP 4 inner: drives the atom; owns budgets/retries; builds
   │                                metrics_source_content
 R3.M1.5 orchestration ─────────► the spine: sessions, plan_index, work items, 2 barriers, sweep
```

**Six invariants worth holding in mind while reading the flow:**

1. **The atom is reused, parameterized by `context`** — discovery, phase 1, phase 2 map, phase 2
   scrape are the *same* five stages with different tools/budgets (Part 2 table).
2. **The LLM never supplies a URL** — map url is app-injected, scrape url is app-resolved from the
   LLM's opaque `id`; the guard injects and strips before execution.
3. **Two hard barriers, two isolation layers** — discovery finishes before any pipeline (RC8);
   all pipelines finish before R3.M2.5; each pipeline catches its own failure (D5) and
   `return_exceptions=True` backstops an unexpected raise.
4. **`evidence_class` is the only factual/experiential signal** — phase 1 searches every metric via
   `web_target`; phase 2 scrapes only unresolved `factual` metrics (`scrape_target`); experiential
   metrics rely on web evidence + the reviews block (`review_target`) at R3.M2.
5. **Evidence is stored once, attributed many times** — `metrics_source_content` is a flat set of
   items keyed by `(source_kind, url, shaped_text)`; `metric_labels` carries the attribution, so a
   scraped page serving several metrics is one item, while same-url web excerpts with different text
   stay separate.
6. **Tool failures continue; LLM provider failures stop** — a failed tool call becomes a `failed`
   `tool` message and the loop goes on. A `MetricResolutionProviderError` stops the step, ends the
   amenity (discovery: `none` instead), and, when `cause = availability`, moves the run's circuit
   breaker. Once the breaker is open, every later LLM call is skipped (`cause = circuit_open`), and the
   run raises if no pipeline finished its LLM steps.
