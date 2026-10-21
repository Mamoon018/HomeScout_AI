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
([R3_Specific_Metric_Resolution_spec.md:518](R3_Specific_Metric_Resolution_spec.md)).
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
│          → website_search_results[(cat,place)] = {website_url|None, origin}
│          ╌╌╌ barrier: ALL verdicts ready before any pipeline starts (RC8) ╌╌╌
│
├─ STEP 4  AMENITY PIPELINES  (R3.M1.4 + R3.M2.2–R3.M2.4)    ── concurrent, under bounds
│          results = await asyncio.gather(*tasks, return_exceptions=True)
│          each pipeline: phase1_loop → triage → (cond.) phase2_loop → R3.M2.2–2.4
│          ╌╌╌ HARD BARRIER: gather returns only when ALL N pipelines finished ╌╌╌
│
├─ STEP 5  Post-gather sweep (Exception → synthesize all-unresolved record)  [D5]
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
- Where `metrics_source_content` is written, and how dedup + fan-out happens in phase 2.

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
│        OpenAI → Groq chain (same LLM_PROVIDER_ORDER). tools-only; NO response_format.              │
│        out: assistant message + optional tool_calls                                                │
│        │                                                                                           │
│        ▼                                                                                           │
│  ③ [R3.M1.1 · Step 2]  GUARD PROPOSED CALLS   (whole-message, all-or-nothing)                      │
│        no calls → no_tool_calls · outer fields + unique ids → invalid_call_structure               │
│        name ∈ catalog? no → out_of_catalog · decode arg JSON → schema validate → in_catalog        │
│        additional validator (metric_label ∈ metric set; scrape id ∈ issued set) via validation_ctx │
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
│        per-server semaphore (Parallel=4 / Firecrawl=2) + per-call timeout + typed retry;           │
│        Firecrawl ALSO paced by token bucket ≤10/min. is_error / dropped-SSE / 429 → typed outcome. │
│        │                                                                                           │
│        ▼                                                                                           │
│  ⑤ [R3.M1.2]  SHAPE RESULT  → exactly ONE `tool` message per call                                  │
│        ordered guard: terminated cleanly? NO → failed                                              │
│                                            YES → has content? → ok(result) : empty                 │
│        (failed = retry-eligible · empty = TERMINAL, never retried · result always passed through)  │
│        │                                                                                           │
│        ▼                                                                                           │
│   append `tool` message to the amenity conversation (tool_call_id order)                           │
│   + write shaped_text into metrics_source_content[label][(source_kind,url)]  (phase 1 / phase 2)   │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Context parameterization of the atom:**

| Phase / step | `context` | Exposed tool(s) | LLM sets | App injects | Budget (per R3.M1.4 / R3.M1.1) |
|---|---|---|---|---|---|
| Discovery (R3.M1.3) | `website_discovery` | `web_search` | `objective`, `search_queries` | — | 1 call (+1 retry of selection turn only) |
| Phase 1 (R3.M1.4) | `metric_web_search` | `web_search` | `objective`, `search_queries`, `metric_label` | — | 1 search + 1 retry **per metric** |
| Phase 2 map (R3.M1.4) | `site_map` | `firecrawl_map` | *(nothing)* | homepage `url` | 1 map (+1 retry) |
| Phase 2 scrape (R3.M1.4) | `metric_scrape` | `firecrawl_scrape` | candidate `id`, `metric_label`(s) | real `url`, `formats` | 1 scrape/unresolved metric, dedup→≤8 distinct, +1 retry each |

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
│                                                                                                 │
│  tasks = [ discover_search(wi) for wi in declined ]   ;   await asyncio.gather(*tasks)           │
│  (barrier waits on declined subset only; pass-items already in dict → RC8 holds for all N)       │
│                                                                                                 │
│  ┌─ discover_search(wi) ── Stage 1 only; gate already applied in pre-pass ───────────────────┐  │
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
│ │  ╔═ PHASE 1 LOOP ═ [R3.M1.4] ════ web_search rounds until no tool_calls OR budget spent ═══╗ ││
│ │  ║ instruction: amenity identity + website_url(if any) + every metric                      ║ ││
│ │  ║   (label, question, value_type, unit, enum_values, verification, web target);           ║ ││
│ │  ║   "search all metrics, tag each call with metric_label";                                ║ ││
│ │  ║   if website_url present: ≥1 host-scoped query ALONGSIDE off-site queries (D7)           ║ ││
│ │  ║                                                                                          ║ ││
│ │  ║   repeat:                                                                                ║ ││
│ │  ║     ╭─ TOOL-TURN CYCLE (atom), context = metric_web_search ───────────────────────────╮ ║ ││
│ │  ║     │ ① catalog(web_search; +metric_label)  ② call_turn  ③ guard(metric_label ∈ set)  │ ║ ││
│ │  ║     │ LOOP budget check BEFORE execute: metric with no attempt left → not executed     │ ║ ││
│ │  ║     │ ④ gateway web_search ×calls via gather (Parallel sem)  ⑤ shape ok/empty/failed   │ ║ ││
│ │  ║     ╰────────────────────────────────────────────────────────────────────────────────╯ ║ ││
│ │  ║     append tool msgs → write evidence into metrics_source_content[label][(web,url)]      ║ ││
│ │  ║     retry: failed/timeout/guard-reject → 1 retry · empty = TERMINAL (burns budget)       ║ ││
│ │  ║   metric budget spent when its search terminates clean (ok OR empty) or retry used       ║ ││
│ │  ╚═══════════════════════════════════════════════════════════════════════════════════════╝ ││
│ │                               │ (same shared message list)                                   ││
│ │                               ▼                                                              ││
│ │  ╔═ TRIAGE ═ [R3.M1.4] ══ separate STRICT-schema NO-tools request [C3.1.2 call_structured] ╗ ││
│ │  ║   returns {metric_label, status ∈ sufficient|unresolved} per metric                      ║ ││
│ │  ║   label-set checked · schema/invalid → retry up to 2× · still bad → ALL unresolved       ║ ││
│ │  ║   coverage: a metric no phase-1 call was tagged with → unresolved (app-set, ignores LLM)  ║ ││
│ │  ║   evidence all-empty OR all-failed → unresolved  (empty/failed distinction kept for M2)   ║ ││
│ │  ╚═══════════════════════════════════════════════════════════════════════════════════════╝ ││
│ │                               │                                                              ││
│ │             ┌─────────────────┴─ phase-2 gate ─────────────────┐                             ││
│ │       ≥1 metric unresolved AND website_url ≠ None ?             │                             ││
│ │             │ NO → SKIP phase 2 (every metric sufficient, or no URL → web-only)              ││
│ │             │ YES                                                                            ││
│ │             ▼                                                                                ││
│ │  ╔═ PHASE 2 LOOP ═ [R3.M1.4] ═ map → select → scrape  (D1, uniform tool loop, not a crawl) ╗ ││
│ │  ║                                                                                          ║ ││
│ │  ║  (a) MAP — first phase-2 call is firecrawl_map                                           ║ ││
│ │  ║      ╭─ atom, context = site_map · app injects url = official homepage ───────────────╮  ║ ││
│ │  ║      │ ① catalog(firecrawl_map, no LLM args) ② call_turn ③ guard ④ gateway(Firecrawl) │  ║ ││
│ │  ║      │ ⑤ shape → link set                                                              │  ║ ││
│ │  ║      ╰──────────────────────────────────────────────────────────────────────────────╯  ║ ││
│ │      app shapes links → (id,url) CANDIDATE LIST, capped at 50, opaque ids fresh per map     ║ ││
│ │  ║      map failed/timeout → 1 retry → then GIVE UP phase 2 (metrics stay on web evidence)  ║ ││
│ │  ║                                                                                          ║ ││
│ │  ║  (b) SELECTION TURN — LLM emits firecrawl_scrape calls, ONE page per unresolved metric   ║ ││
│ │  ║      each call: id (NEVER url) + required metric_label(s) (≥1, list allowed)             ║ ││
│ │  ║      guard: id ∈ issued set? · ≥1 metric_label? (untagged → reject, no orphan)           ║ ││
│ │  ║      selection invalid → 1 retry → still invalid → empty selection → web-only            ║ ││
│ │  ║                                                                                          ║ ││
│ │  ║  (c) DEDUP + FAN-OUT CYCLE  — the one place page↔metric many-to-many is resolved         ║ ││
│ │  ║      1 collect (metric_label, id) requests                                               ║ ││
│ │  ║      2 resolve id → real url via candidate list                                          ║ ││
│ │  ║      3 dedup by url → one firecrawl_scrape per unique url (union of requesting metrics)   ║ ││
│ │  ║      4 ceiling: >8 distinct urls → drop surplus (those metrics stay on web evidence)      ║ ││
│ │  ║      5 FETCH ONCE — ≤8 scrapes concurrent (Firecrawl sem); app substitutes real url,     ║ ││
│ │  ║        strips metric_label  → ④ gateway → ⑤ shape ; each url's ok/empty/failed+retry once ║ ││
│ │  ║        scrape failed/timeout → 1 retry → still failed → skip page (amenity survives)      ║ ││
│ │  ║        scrape empty → appended, loop continues, NOT retried, NOT a skip                   ║ ││
│ │  ║      6 FAN OUT after results — write single shaped result under EACH requesting metric's  ║ ││
│ │  ║        key: metrics_source_content[label][(scrape,url)]  (identical text per metric)      ║ ││
│ │  ║  no second triage · successful phase 2 not repeated                                      ║ ││
│ │  ╚═══════════════════════════════════════════════════════════════════════════════════════╝ ││
│ │                               │                                                              ││
│ │                               ▼  returns: conversation + metrics_source_content             ││
│ │  ┌─ HAND-OFF TO R3.M2 (per amenity; M1 focus ends here) ─────────────────────────────────┐ ││
│ │  │ metrics_source_content = { label: { (source_kind,url): {shaped_text, retrieved_at} } } │ ││
│ │  │   + amenity-level Google-reviews block {shaped_text, retrieved_at} (no metric)         │ ││
│ │  │ R3.M2.2 resolution turn (reads buckets, NOT the thread; strict schema, no tools)       │ ││
│ │  │   → R3.M2.3 conform + verification gate → R3.M2.4 provenance (quote ∈ bucket)          │ ││
│ │  │   → SpecificMetricsRecord                                                              │ ││
│ │  └────────────────────────────────────────────────────────────────────────────────────┘ ││
│ │                                                                                              ││
│ │  try:    return SpecificMetricsRecord(resolved/unresolved metrics)                           ││
│ │  except: return SpecificMetricsRecord(all metrics unresolved)   [D5 — failure isolated here] ││
│ └──────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                 │
│  ╌╌╌╌╌ HARD BARRIER: gather returns only when ALL N pipelines finished (a failure still         │
│         "finished" — it returned a record). return_exceptions=True → unexpected raise comes      │
│         back as a value, not a cancel of siblings ╌╌╌╌╌                                          │
└─────────────────────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                                 │
┌─ STEP 5  POST-GATHER SWEEP (single-threaded, after barrier) ────────────────────────────────────┐
│  for r in results:  isinstance(r, Exception) → synthesize all-unresolved record [D5 safety net]  │
│                     else → r is a SpecificMetricsRecord                                          │
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

**Three invariants worth holding in mind while reading the flow:**

1. **The atom is reused, parameterized by `context`** — discovery, phase 1, phase 2 map, phase 2
   scrape are the *same* five stages with different tools/budgets (Part 2 table).
2. **The LLM never supplies a URL** — map url is app-injected, scrape url is app-resolved from the
   LLM's opaque `id`; the guard injects and strips before execution.
3. **Two hard barriers, two isolation layers** — discovery finishes before any pipeline (RC8);
   all pipelines finish before R3.M2.5; each pipeline catches its own failure (D5) and
   `return_exceptions=True` backstops an unexpected raise.
