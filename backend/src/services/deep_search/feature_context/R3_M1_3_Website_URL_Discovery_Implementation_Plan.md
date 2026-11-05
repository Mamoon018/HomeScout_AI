# R3.M1.3 — Resolve the Official Website URL Before the Loop — Implementation Plan

## Context

**Why.** We are building Responsibility 3 (*Specific Metric Resolution*) of Deep Search one
sub-component at a time. The responsibility class `SpecificMetricResolution` exists only as a
promotion skeleton — `run_specific_metric_resolution` raises `NotImplementedError`
([specific_metric_resolution.py:52](../specific_metric_resolution.py)).
Its client prerequisites are built and tested: the MCP gateway **C3.1.1**
([mcp_tools.py](../../../clients/mcp_tools.py)), the shared tool-turn caller **C3.1.2**
([llm_provider.py](../../../clients/llm_provider.py)), and the phase catalog + call guard
**R3.M1.1** ([phase_tool_catalog.py](../phase_tool_catalog.py)).

**What this plan builds.** `run_specific_metric_resolution(state)` **only to the extent of
STEP 3** of the complete M1 traceflow ([R3_M1_Traceflow.md](R3_M1_Traceflow.md) Part 3):
open gateway → STEP 1 `plan_index` → STEP 2 work items → **STEP 3 = R3.M1.3 discovery batch** →
close gateway. STEP 1 and STEP 2 are deterministic join/eligibility code built minimally as the
spine that feeds STEP 3. STEP 4 pipelines (R3.M1.4), STEP 5 sweep, STEP 6 combine (R3.M2) are
**out of scope** and are not built; the method returns `state` with the three discovery stores
populated and `state.amenity_records` still `None`.

**R3.M1.3 in one line.** Before the per-amenity loop runs, produce, for every work item, a
resolved `website_search_results` verdict (`website_url` + `website_origin ∈
google/discovered/none`). Stage 0 is a deterministic `tldextract` official-URL gate over Google's
`PredefinedMetricsRecord.website`; declined items fall through to Stage 1 — one LLM-built
`web_search` + a structured candidate-id selection turn that resolves to a real URL or `none`. The
LLM never emits a URL (id-indirection makes hallucination impossible by construction). Spec:
[R3_Specific_Metric_Resolution_spec.md](R3_Specific_Metric_Resolution_spec.md) R3.M1.3 (lines
436–514) and traceflow Part 3a (lines 298–341).

**Dependencies this uses (no new ones invented).** C3.1.1 `search_web` + `get_tool_definitions`;
C3.1.2 `call_turn` + `call_structured`; R3.M1.1 `build_tool_catalog("website_discovery")` +
`guard_proposed_calls(...)`. R3.M1.2 (result shaping) is **not** a dependency of R3.M1.3 (the
mermaid graph confirms `s314` does not feed `s315`); discovery reads the gateway's typed
`WebSearchResult | ToolFailure` directly.

---

## 1. File and Module Structure (Build work — these become the `todos`)

| # | File | New/Mod | Purpose / ownership |
|---|---|---|---|
| 1 | `backend/requirements.txt` | Mod | Add a pinned `tldextract==<exact>`; vendor an **offline PSL snapshot** directory under the package so the gate never fetches at runtime. |
| 2 | `backend/src/services/deep_search/feature_schemas/schemas.py` | Mod | Add data contracts `WebsiteSearchResult`, `DiscoveryCandidate`, `DiscoverySearchRecord`, `OfficialGateRecord`; the selection wire model `WebsiteSelectionResult` + `website_selection_json_schema()` + `WEBSITE_SELECTION_SCHEMA_NAME`; add 3 fields to `AmenitySearchState`. |
| 3 | `backend/src/services/deep_search/official_url_gate.py` | New | **R3.M1.3 Stage 0.** Pure deterministic gate: module-level offline `TLDExtract`, `DENYLIST`, `compact`/`match`, `official_url_gate(website, name) -> GateOutcome`. Isolated because of the `tldextract`/PSL dependency + independent audit telemetry. |
| 4 | `backend/src/services/deep_search/feature_prompts/website_discovery_instruction.py` | New | R3.M1.3 prompt content: `build_discovery_search_instruction(...)` (the `web_search` tool turn) and `build_website_selection_instruction(...)` (the structured selection turn). Content only, no logic — matches `feature_prompts/` convention. |
| 5 | `backend/src/services/deep_search/specific_metric_resolution.py` | Mod | Implement `run_specific_metric_resolution` to STEP 3; the STEP 1/2 spine methods; the STEP 3 discovery-batch orchestration (sync Stage-0 pre-pass + async fan-out); and the R3.M1.3 Stage-1 discovery stage methods. |
| 6 | `backend/src/services/deep_search/feature_tests/test_r3_m1_3_website_url_discovery.py` | New | §4.2 dummy-provider fixtures + gate unit tests (deterministic code-path rules). |
| 7 | `backend/src/services/deep_search/feature_sample_runs/r3_m1_3_website_url_discovery_sample_run.py` | New | §4.1 **live** stage-by-stage sample runner (one real discovery, seeded handoff state). |

Writing this plan markdown is **not** a build todo. No new exception class is needed: catalog
misbuild reuses `MetricResolutionValidationError`; selection-turn provider exhaustion reuses
`MetricResolutionProviderError`; all discovery failures **degrade to `none`** (D5), they do not
raise out of a task.

---

## A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: DeepSearch — coordinates responsibilities (unchanged; not wired to R3 yet)
   └─ Responsibility: SpecificMetricResolution — resolve specific metrics (class exists)
      └─ run_specific_metric_resolution(state) — SPINE, built to STEP 3 only
         ├─ STEP 0  open gateway + capture raw_tool_definitions           [C3.1.1]
         ├─ STEP 1  _build_plan_index(state)            — category_id → CategoryMetricPlan
         ├─ STEP 2  _derive_work_items(state, plan_index) — RC7 eligibility (N items)
         ├─ STEP 3  Mechanism R3.M1.3 Workflow: Website-URL Discovery Batch
         │   ├─ Stage 0: _discovery_pre_pass(...)        — sync gate over ALL items
         │   │             └─ official_url_gate(website, name)   [official_url_gate.py]
         │   └─ Stage 1: _discover_website_url(wi, rec)  — async, declined subset only
         │         ├─ _run_discovery_search(rec)         — catalog→turn→guard→search(+1 retry)
         │         ├─ (pure) _index_candidates(result)   — drop url=None, c1..cN, id→url map
         │         ├─ _select_candidate(name, addr, cands)— structured turn (+1 retry)
         │         └─ (pure) _resolve_verdict(sel, map)  — null/∉map→none · ∈map→discovered
         └─ STEP 0' close gateway (finally)                                [C3.1.1]
      └─ (STEP 4 R3.M1.4 / STEP 5 / STEP 6 R3.M2 — OUT OF SCOPE, not built)
```

> Annotated nodes: `official_url_gate` is a **module function** (pure, own dependency), not a
> method; `_index_candidates` / `_resolve_verdict` are **pure helpers**. The gate telemetry store
> and selection schema are **contracts** (§B), not runtime methods.

## B. Data Contracts

New (in `feature_schemas/schemas.py`). Keying follows the spec's `(category_id, place_id)` tuple
for the three discovery stores (distinct from the existing nested-dict convention, as the spec
specifies).

| Contract | Purpose | Fields (`name: type — meaning`) | Mutability | Created by → Read by |
|---|---|---|---|---|
| `WebsiteSearchResult` | the per-item verdict (the Step-4 handoff) | `website_url: str \| None` · `website_origin: Literal["google","discovered","none"]` | immutable | Stage0/Stage1 → STEP 4 (future) |
| `DiscoveryCandidate` | one indexed search hit | `id: str` (c1..cN) · `url: str` · `title: str \| None` · `text: str` | immutable | `_index_candidates` → selection turn, telemetry |
| `DiscoverySearchRecord` | Stage-1 eval telemetry | `objective: str` · `search_queries: tuple[str,...]` · `candidates: tuple[DiscoveryCandidate,...]` · `selected_id: str \| None` · `resolved_url: str \| None` · `retrieved_at: str` | immutable | Stage1 → `state.discovery_search_results` |
| `OfficialGateRecord` | Stage-0 eval telemetry (ALL items) | `name, website, host, registered_domain, sld, suffix, compact_name, compact_sld: str \| None` · `verdict: Literal["official","discovery"]` · `reason_code: str` | immutable | Stage0 → `state.official_gate_results` |
| `WebsiteSelectionResult` | **pydantic wire model** for the selection turn | `selected_id: str \| None` — a candidate id or the `none` sentinel; **never a URL** | immutable | provider body → `_resolve_verdict` |

`reason_code ∈ {presence_empty, no_registrable_domain, denylist_hit, sld_match, sld_no_match}`
(spec line 498). Fields not applicable to a `reason_code` are `None`.

**Mutated object — `AmenitySearchState`** ([schemas.py:1021](../feature_schemas/schemas.py)),
3 new fields appended (default empty dict):

| Field | Type | Written by | Coverage |
|---|---|---|---|
| `website_search_results` | `dict[tuple[int,str], WebsiteSearchResult]` | Stage 0 (google) + Stage 1 (discovered/none) | ALL N items |
| `discovery_search_results` | `dict[tuple[int,str], DiscoverySearchRecord]` | Stage 1 | declined subset that searched |
| `official_gate_results` | `dict[tuple[int,str], OfficialGateRecord]` | Stage 0 pre-pass | ALL N items |

Reused contracts (no change): `RawToolDefinitions`, `WebSearchResult`, `SearchExcerpt`,
`ToolFailure` (C3.1.1); `AssistantTurn`, `ToolCall` (C3.1.2); `GuardDecision`, `ValidatedCall`
(R3.M1.1); `PredefinedMetricsRecord`, `CategoryMetricPlan`.

Internal (in `specific_metric_resolution.py`, not persisted): `_DiscoveryWorkItem(category_id,
place_id, taxonomy_node, depth, specific_metrics)` — STEP 2 output; carries only the key fields,
discovery inputs are read from `rec` (the `PredefinedMetricsRecord`) per spec line 449.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract (methods used) | Impl | Depended on by |
|---|---|---|---|---|
| `ToolGateway` | Protocol (C3.1.1) | `open()` · `get_tool_definitions() -> RawToolDefinitions` · `search_web(objective, search_queries) -> WebSearchResult \| ToolFailure` · `aclose()` | `McpToolGateway` | spine + Stage 1 |
| `StructuredLLMCaller` | class (C3.1.2) | `call_turn(messages, tools, tool_choice, stage, provider_error_cls) -> AssistantTurn` · `call_structured(instruction, user_content, json_schema, schema_name, stage, provider_error_cls) -> (dict, str)` | one (bound chain) | Stage 1 |
| `build_tool_catalog` | fn (R3.M1.1) | `(raw_tool_definitions, "website_discovery") -> list[dict] [raises MetricResolutionValidationError]` | one | Stage 1 |
| `guard_proposed_calls` | fn (R3.M1.1) | `(proposed_tool_calls, tool_catalog, "website_discovery", None) -> GuardDecision` | one | Stage 1 |
| `official_url_gate` | fn (new) | `(website: str \| None, name: str \| None) -> GateOutcome` — pure, total | one | Stage 0 |
| `TLDExtract` | lib (new dep) | `extractor(host) -> (sub, sld, suffix)`; offline, pinned PSL | module singleton | `official_url_gate` |
| prompt builders | fns (new) | `build_discovery_search_instruction(name, address)` · `build_website_selection_instruction(name, address, candidates, json_schema)` | one | Stage 1 |

`GateOutcome` (dataclass in `official_url_gate.py`): `verdict`, `reason_code`, and the operand
fields (`host, registered_domain, sld, suffix, compact_name, compact_sld`) the pre-pass copies
straight into `OfficialGateRecord` — so the gate is defined once and the orchestrator only records.

## D. Class & Method Blueprint

**`SpecificMetricResolution`** — Responsibility 3; already holds `_tool_gateway` + `_llm_caller`.
STEP 3 build adds the spine + Stage-1 methods. `DISCOVERY_CONCURRENCY = SEARCH_CONCURRENCY` (4) is
added as a module constant (the fan-out bound; discovery runs under the Parallel pool).

| Method | Signature | Purpose (one line) |
|---|---|---|
| `run_specific_metric_resolution` | `(state: AmenitySearchState) -> AmenitySearchState [mutates: state.website_search_results, .discovery_search_results, .official_gate_results]` | open → spine → STEP 3 discovery batch → close; built to STEP 3 only |
| `_build_plan_index` | `(state) -> dict[int, CategoryMetricPlan]` | STEP 1: index plans by `category_id` once |
| `_derive_work_items` | `(state, plan_index) -> list[_DiscoveryWorkItem]` | STEP 2 (RC7): one item per `(cat, place)` whose category has ≥1 `specific_metrics` |
| `_run_discovery_batch` | `(state, work_items, raw_tool_definitions) -> None [mutates: the 3 stores]` | STEP 3: run pre-pass, fan out declined, merge results after barrier |
| `_discovery_pre_pass` | `(state, work_items) -> list[_DiscoveryWorkItem]` | Stage 0: gate every item; write google verdicts + `official_gate_results`; return declined |
| `_discover_website_url` | `(wi, rec, raw_tool_definitions) -> tuple[WebsiteSearchResult, DiscoverySearchRecord \| None]` | Stage 1 coroutine for one declined item |
| `_run_discovery_search` | `(rec, raw_tool_definitions) -> WebSearchResult \| None` | catalog → `call_turn` → guard → `search_web`; 1 retry on tool failure; `None` on give-up |
| `_select_candidate` | `(name, address, candidates) -> str \| None` | structured selection turn; 1 retry on invalid verdict; returns `selected_id` or `None` |

Module-level pure helpers (same file): `_index_candidates(result: WebSearchResult) ->
tuple[tuple[DiscoveryCandidate,...], dict[str,str]]`; `_resolve_verdict(selected_id, id_url_map)
-> WebsiteSearchResult`.

**`official_url_gate.py`** (module):

| Function | Signature | Purpose |
|---|---|---|
| `official_url_gate` | `(website: str \| None, name: str \| None) -> GateOutcome` | ordered gate: presence → host → extract → denylist → SLD match → else |
| `compact` | `(x: str) -> str` | NFKD → drop marks → casefold → keep `[a-z0-9]` |
| `_match` | `(cn: str, cs: str) -> bool` | both `≥ MIN_LEN(5)` and (`cn in cs` or `cs in cn`) |

**`feature_schemas/schemas.py`** adds `website_selection_json_schema() -> dict` (builds
`WebsiteSelectionResult.model_json_schema()` then `_apply_strict_object_rules`, matching the
existing `*_json_schema()` pattern) and `WEBSITE_SELECTION_SCHEMA_NAME = "website_selection"`.

## E. Runtime Flow — Data Object Journey (the request path)

| # | Stage method | Reads | Produces / mutates | Object shape after |
|---|---|---|---|---|
| 1 | `run_...` open | `state` | gateway open; `raw_tool_definitions = gateway.get_tool_definitions()` (local) | sessions live |
| 2 | `_build_plan_index` | `state.category_metric_plans` | `plan_index` (local) | `{cat → CategoryMetricPlan}` |
| 3 | `_derive_work_items` | `state.discovered_places`, `plan_index` | `work_items` (local, N) | `[_DiscoveryWorkItem,...]` |
| 4 | `_discovery_pre_pass` | each `rec = state.predefined_records[cat][place]` | per item: gate → `official` writes `website_search_results[key]={website, google}`; `discovery` → declined. **All** → `official_gate_results[key]` | stores partly filled; `declined` list |
| 5 | `_discover_website_url` (×declined, gathered) | `rec.name`, `rec.address` | returns `(WebsiteSearchResult, DiscoverySearchRecord\|None)` per item | — |
| 5a | `_run_discovery_search` | `rec`, `raw_tool_definitions` | `build_tool_catalog` → `call_turn` → `guard_proposed_calls` → `search_web` | `WebSearchResult` or `None` |
| 5b | `_index_candidates` | `WebSearchResult.excerpts` | drop `url is None`; `c1..cN`; `candidates` + `id→url` map | `(candidates, id_url_map)` |
| 5c | `_select_candidate` | `name, address, candidates` | `call_structured(WEBSITE_SELECTION)` → `WebsiteSelectionResult` | `selected_id` or `None` |
| 5d | `_resolve_verdict` | `selected_id, id_url_map` | verdict | `WebsiteSearchResult{url\|None, discovered\|none}` |
| 6 | `_run_discovery_batch` merge | gathered results / exception slots | write `website_search_results[key]` + `discovery_search_results[key]` for declined | all 3 stores complete (RC8) |
| 7 | `run_...` close | — | `gateway.aclose()` in `finally` | `return state` |

**Transformation trace (shape only):**
```
work_item(cat, place)  ─ rec = predefined_records[cat][place]
 → official_url_gate(rec.website, rec.name) → GateOutcome{verdict, reason_code, operands}
   ├─ official  → WebsiteSearchResult{rec.website, "google"}            (no search)   + OfficialGateRecord
   └─ discovery → (Stage 1):
        WebSearchResult{excerpts[]}            # search_web; ToolFailure→1 retry→None
         → candidates[DiscoveryCandidate{id,url,title,text}] + {id→url}
         → dict (selection body) → WebsiteSelectionResult{selected_id|null}
            ├─ null / selected_id ∉ map (after 1 selection retry) → WebsiteSearchResult{None, "none"}
            └─ selected_id ∈ map                                   → WebsiteSearchResult{map[id], "discovered"}
        + DiscoverySearchRecord (telemetry)    + OfficialGateRecord (written in pre-pass)
   (task exception / timeout / None search / provider-exhaustion) → WebsiteSearchResult{None, "none"}
```

**Approach at the real decision points:**
- *Barrier / RC8 (spec lines 505–512):* Stage 0 is a **synchronous** pre-pass over all work items
  (zero I/O) that writes every `official` verdict immediately and collects the `discovery` subset.
  The fan-out is one coroutine **per declined item**, each `async with discovery_sem`, awaited by a
  single `asyncio.gather(*tasks, return_exceptions=True)` — the barrier. Pass-items are already in
  the dict, so when the barrier returns every item has a verdict. Tasks return their results; the
  orchestrator writes the stores **after** the barrier (single-threaded), so no task mutates shared
  state during the gather.
- *Search retry (spec line 484 "Failure vs empty"):* `search_web` → `ToolFailure` → one re-issue of
  the same call → still `ToolFailure` → `None` (→ verdict `none`). The gateway's own transient
  retries are internal to `search_web`; this is the one R3.M1.3-level search retry.
- *Selection retry:* a `none` sentinel is a **confident terminal** (no retry). An **invalid verdict**
  — schema-invalid body, or a `selected_id` not in the issued `id→url` map — is treated as failed →
  **one retry of the selection turn only** (re-send the same indexed candidates; no second
  `web_search`) → still invalid → `none`.
- *Selection anti-hallucination (spec lines 490–493):* the LLM is shown `candidates` (ids + title +
  snippet; url shown only for judgment) and returns one `selected_id` or `null`. The app resolves
  `id → url` from its own map; a hallucinated host is impossible by construction. This is a body-level
  check **in R3.M1.3**, explicitly **not** the R3.M1.1 tool-call guard (which only validates the
  `web_search` tool turn).
- *Provider fallback:* `call_turn` / `call_structured` try the bound OpenAI→Groq order (C3.1.2);
  exhaustion raises `MetricResolution*Error`, caught inside the task → `none` (D5). Selection runs
  under strict mode, so a decodable-but-schema-invalid body cannot occur; a `None` `selected_id` is
  the normal sentinel, not an error.

## F. Method Detail (non-obvious only)

**`official_url_gate`** (traceflow Part 3a lines 307–322)
- **What it does, in order:** (0) `website` empty/whitespace → `discovery`, `presence_empty`. (1)
  `urlsplit(website).netloc` → lower, strip userinfo/port, `rstrip('.')`. (2)
  `sub, sld, suffix = extractor(host)`; no sld or no suffix → `discovery`, `no_registrable_domain`;
  else `registered_domain = f"{sld}.{suffix}"`. (3) `registered_domain ∈ DENYLIST` → `discovery`,
  `denylist_hit` (fast-reject only). (4) `_match(compact(name), compact(sld))` → `official`,
  `sld_match`. (5) else → `discovery`, `sld_no_match`.
- **Total/pure:** never raises; it is called inside the sync pre-pass. A malformed record that makes
  `urlsplit`/`extractor` raise is caught by `_discovery_pre_pass` and routed to **declined**, never
  to `none` (spec line 508).
- **Library config (locked, spec line 477):** one module-level `TLDExtract(cache_dir=<vendored
  snapshot>, suffix_list_urls=[])`, `include_psl_private_domains=True`. Never fetches at runtime.
- **Business invariant (strict by asymmetry):** a false `official` is expensive and uncorrectable; a
  false `discovery` is cheap. Anything ambiguous → `discovery`. `DENYLIST` and `MIN_LEN=5` are policy
  constants surfaced in-module.

**`_run_discovery_search`**
- **What it does:** `build_tool_catalog(raw_tool_definitions, "website_discovery")`; build the
  discovery instruction (name + full address verbatim; use only the postal code for locality scope,
  degrade `postal → locality/city → name-only`, spec line 514); `call_turn(tools=catalog,
  tool_choice="required")`; `guard_proposed_calls(..., "website_discovery", None)`; on acceptance
  take the first validated call's `objective`/`search_queries` and `search_web`.
- **Failure:** catalog raise / provider exhaustion / guard rejection / `search_web` `ToolFailure`
  after its one retry → return `None` (caller → `none`), each logged WARN. `validation_context` is
  `None` (discovery has no `metric_label`).

**`_select_candidate`**
- **What it does:** `build_website_selection_instruction(name, address, candidates, schema)`;
  `call_structured(json_schema=website_selection_json_schema(), schema_name=WEBSITE_SELECTION_SCHEMA_NAME,
  stage="r3_m1_3_website_selection", provider_error_cls=MetricResolutionProviderError)`; validate the
  body with `WebsiteSelectionResult.model_validate` (defensive backstop under strict); return
  `selected_id`. Invalid/anomalous body → one retry with the same candidates → still invalid → `None`.

---

## Drift breakdown (one entry per method — drift_analyzer skill)

**`official_url_gate(website, name)`**
- Core: match brand against the SLD label only; decide `official` vs `discovery` by rule.
- Drifts handled: *empty/whitespace website* → **core**, **reject→`discovery`** (`presence_empty`).
  *No registrable domain (IP, localhost, bare host)* → **core**, **reject→`discovery`**
  (`no_registrable_domain`). *Denylisted registrable domain* → **core**, **reject→`discovery`**
  (`denylist_hit`). *Business invariant (asymmetry)* → ambiguous → **`discovery`** by design.
- Left out: URL-scheme/port validity beyond netloc parse — *not live* (only the SLD label matters).
  Trimming/normalizing the brand beyond `compact` — *imaginary* (spec fixes `compact`). Unicode host
  IDNA punycoding — *not live* (compare is on the SLD label; `tldextract` handles it). Network PSL
  refresh — *wrong boundary* (maintenance task, offline snapshot).

**`_discovery_pre_pass(state, work_items)`**
- Core: gate every item; write `google` verdicts + `official_gate_results`; collect declined.
- Drifts handled: *gate raises on a malformed record* → **core**, **recover→declined** (safe default,
  never silent `none`; WARN). *Missing `predefined_records[cat][place]` (precondition)* → **core**,
  **reject→`none`** verdict for that key + `official_gate_results{presence_empty}` (can't discover
  without identity), WARN.
- Left out: concurrency guard — *not live* (synchronous, single-threaded, no I/O). Per-item timeout —
  *wrong boundary* (pure CPU, sub-ms).

**`_run_discovery_batch(state, work_items, raw_tool_definitions)`**
- Core: fan out one coroutine per declined item; merge verdicts after the barrier.
- Drifts handled: *a task raises unexpectedly* → **core**, `gather(return_exceptions=True)` → that
  slot **recover→`none`** verdict (D5), WARN; siblings unaffected. *Unbounded fan-out saturates the
  Parallel pool* → **core**, `discovery_sem` (= `SEARCH_CONCURRENCY`) bounds concurrency;
  `gateway.search_web` adds its own per-server semaphore + rate handling.
- Left out: single-flight / crawl cache across duplicate places — *not live* (D4 revised:
  duplication intentionally accepted, spec line 501). Retry of a whole failed task — *imaginary*
  (retries are owned per-stage inside the coroutine).

**`_discover_website_url` / `_run_discovery_search` / `_select_candidate`**
- Core: one `web_search` + a structured selection → a `discovered` URL or `none`.
- Drifts handled: *`search_web` `ToolFailure`* → **core**, **recover**: 1 retry → else `None`→`none`,
  WARN. *catalog raise / provider exhaustion / guard rejection* → **core**, **recover→`none`**
  (D5), WARN. *empty excerpts / all `url is None`* → **core**, candidates empty → selection yields
  `none`, INFO (not a drift — genuine no-candidate). *hallucinated/invalid `selected_id`* → **core**,
  **recover**: 1 selection retry → else `none` (id-indirection makes a fabricated URL structurally
  impossible). *`none` sentinel* → **core**, **terminal `none`**, not retried (confident decision).
- Left out: normalizing/validating the resolved URL (`HttpUrl`) — *not live* (it is a verbatim
  search-result URL; the phase-2 `firecrawl_map` url is app-injected downstream, spec line 502).
  A second `web_search` on invalid verdict — *wrong response* (spec: selection-turn retry only).

**`_build_plan_index` / `_derive_work_items`**
- Core: index plans; emit one work item per eligible `(cat, place)`.
- Drifts handled: *category in `discovered_places` with no `CategoryMetricPlan`* → **core**,
  **reject** that category from work items (no plan ⇒ no metrics ⇒ not eligible), DEBUG. *Category
  with 0 `specific_metrics` (basic_profile)* → **core**, **reject** (RC7), no work item.
- Left out: validating place/plan field contents — *trust* (upstream M1 contracts guarantee shape).

---

## Logging plan (diagnostic-logger skill — threaded by a batch id + `(cat, place)` key)

- **INFO `r3m1_3.discovery_batch_start`** — `{batch_id, work_items: N}`. Boundary into STEP 3.
- **INFO `r3m1_3.pre_pass_done`** — `{batch_id, official, declined}`. State change (Stage-0 outcome
  distribution); the per-item gate rows live in `state.official_gate_results`, not the log.
- **WARN `r3m1_3.discovery_degraded`** — `{batch_id, key, reason ∈ search_failed | invalid_verdict |
  missing_record | catalog_error | provider_exhausted | task_exception}`. The silent drifts
  (recover→`none`); each is the only evidence that item degraded.
- **INFO `r3m1_3.discovery_resolved`** — `{batch_id, key, origin}` only for `discovered` (a state
  change: a URL was found). `none`-by-sentinel and `google` are not logged per-item (reproducible /
  in the stores) to avoid N-line spam.
- **INFO `r3m1_3.discovery_batch_done`** — `{batch_id, google, discovered, none}`. Boundary out.
- Gateway and provider layers already log their own attempts; R3.M1.3 does not re-log them. No
  secret (API key, bearer) is ever in a record. R3.M1.1's `build_tool_catalog`/guard emit their own
  INFO nodes.

---

## Async map (async_app_skill — placement × ordering decided independently)

| Operation group | I/O touchpoint | Data dependency | Placement | Ordering |
|---|---|---|---|---|
| gateway `open()` / `aclose()` | MCP handshake / teardown | gates everything | event loop (async-native) | sequential `await` (open first, close in `finally`) |
| STEP 1 `_build_plan_index`, STEP 2 `_derive_work_items` | none (in-memory) | needed by STEP 3 | event loop, inline | sequential (trivial CPU) |
| Stage 0 pre-pass + `official_url_gate` | **none** (pure) | feeds the fan-out | event loop, **inline** (sub-ms CPU, no thread/process) | sequential loop over all items |
| Stage 1 fan-out (`_discover_website_url` × declined) | `search_web`, `call_turn`, `call_structured` | **independent across items** | event loop, async-native | **concurrent** `gather`, bounded by `discovery_sem` |
| within one discovery coroutine | search → selection | selection needs search result | event loop | **sequential** `await` (A → await → B) |

- **Shared-state model:** partial-results-and-merge. Each coroutine returns `(key, verdict,
  telemetry)`; the orchestrator writes the three stores **after** the barrier, single-threaded — no
  concurrent mutation. (`asyncio` is cooperative, but returning-then-merging keeps "writes NO shared
  state" literally true and race-proof.)
- **No offload:** every I/O call is already async-native (gateway, caller), so it stays on the event
  loop; the only CPU (gate, indexing) is trivial and pure, so it runs inline. No thread, no process.
- **Bound:** `discovery_sem = asyncio.Semaphore(DISCOVERY_CONCURRENCY=SEARCH_CONCURRENCY)`; the
  gateway's own `_search_sem` (4) + reactive 429 handling back it. The barrier's latency scales with
  the declined subset, not N (spec line 512).

---

## 4. Sample Runner and Fixtures

### 4.1 Live sample runner (required) — `feature_sample_runs/r3_m1_3_website_url_discovery_sample_run.py`
- **Run:** from `backend/`: `python -m
  src.services.deep_search.feature_sample_runs.r3_m1_3_website_url_discovery_sample_run`
  (needs `PARALLEL_API_KEY` for the live `open()` + billed search, `OPENAI_API_KEY`/`GROQ_API_KEY`
  for the two LLM turns; `tldextract` installed + the vendored PSL present).
- **Seeds:** dummy handoff state **as after M1.3** — two seeded `PredefinedMetricsRecord`s in
  `state.predefined_records` + matching `discovered_places` + one `CategoryMetricPlan` with ≥1
  `specific_metrics`, hand-built inline (no earlier mechanism is called). One record carries a
  Google `website` that **passes** the gate (proves Stage-0 `official`, zero cost); one carries a
  **declined** `website` (empty or an aggregator host) to force Stage 1 live. The seeded identities
  are **fresh venues**, not reused from any prompt worked-pair or the R3.M1.1 runner's seed.
- **Prints (titled section per stage):** input state; `plan_index`; work items; Stage-0 gate
  decisions + `official_gate_results`; for the declined item — catalog, discovery instruction,
  `call_turn` provider attempts + proposed args, guard decision, live `search_web` excerpt count,
  indexed candidates + `id→url` map, selection instruction, `call_structured` provider attempts +
  body, resolved verdict; final `website_search_results` / `discovery_search_results`. On a typed
  failure: class, `stage`, message, non-zero exit. Reads provider-attempt / raw-body logs via a
  `_RecordCollector` exactly as `r3_m1_1_tool_catalog_guard_sample_run.py` does. Writes nothing to
  disk; closes gateway + caller in `finally`.

### 4.2 Dummy-provider fixtures (pytest) — `feature_tests/test_r3_m1_3_website_url_discovery.py`
No live calls. A fake `StructuredLLMProvider` / fake `ToolGateway` drive the deterministic rules:
- **Gate unit tests:** `official` on SLD match (incl. buried `clinic.reseller.brand.co.uk`);
  `discovery` on `brand.evil.com`, empty website, IP/localhost, denylist hit; `compact` folds
  accents (`"Café México"→cafemexico`); `MIN_LEN` blocks short spurious hits;
  `include_psl_private_domains` → `brand.wixsite.com` is `official`.
- **Stage-1 code paths:** id-indirection drops `url is None`; `selected_id ∈ map` → `discovered` +
  verbatim URL; `null` → `none` (no retry); invalid `selected_id` → one selection retry → `none`;
  `search_web` `ToolFailure` → one retry → `none`; a task exception slot → `none` (D5).
- **Orchestration:** pre-pass writes `official_gate_results` for **all** items and
  `discovery_search_results` only for the searched subset; a malformed record → declined (not
  `none`); RC8 — every work item has a verdict after the barrier; RC7 eligibility (basic_profile
  category produces no work item).

---

## Architecture & Modularity Decisions (Implementation_architecture_skill — Section 7 format)

### Layer 1 — Glance
- **Shape:** R3.M1.3 is a set of **stage methods on the existing `SpecificMetricResolution`
  responsibility class** plus one **pure module** (`official_url_gate.py`) and one **prompt module**,
  reusing three already-built abstractions (C3.1.1 gateway behind the `ToolGateway` Protocol, C3.1.2
  caller, R3.M1.1 catalog/guard functions). No new class, no new service.
- **Seams (what varies independently):** the **official-URL gate** (`tldextract`/PSL + `DENYLIST`
  isolated in its own module, audited via `official_gate_results`); the **LLM provider chain**
  (behind C3.1.2's OpenAI→Groq order); the **MCP servers** (behind the `ToolGateway` Protocol); the
  **prompt content** (behind the prompt module, editable without touching logic).
- **Components:** `SpecificMetricResolution` (spine + Stage-1 orchestration) · `official_url_gate`
  (Stage-0, pure) · `website_discovery_instruction` (prompt content) · discovery contracts + 3 state
  fields (schemas).

### Layer 2 — Component Map / Decisions / Kept-concrete

**B. Component map**

| Component | Owns | Depends on | Abstracted? |
|---|---|---|---|
| `SpecificMetricResolution` (STEP 3) | spine + Stage-1 discovery orchestration | ToolGateway, StructuredLLMCaller, R3.M1.1 fns, `official_url_gate`, prompts | — (concrete) |
| `official_url_gate.py` | Stage-0 deterministic gate + telemetry operands | `tldextract` (offline PSL), stdlib `urlsplit` | — (concrete module fn) |
| `website_discovery_instruction.py` | prompt text for both discovery turns | schemas (for the selection schema render) | — (content) |
| discovery contracts + state fields | verdict + telemetry shapes | — | — (data) |
| `ToolGateway` | typed MCP ops | — | Yes: Protocol (test seam; 2 impls: real + fake) — pre-existing C3.1.1 |

**C. Decisions & justifications**

| Decision | Current requirement that forced it | What breaks today without it |
|---|---|---|
| New module `official_url_gate.py` | the gate needs a pinned offline `tldextract` + vendored PSL + its own audit telemetry (spec lines 51–54, 495–499) | the dependency + PSL config leaks into the responsibility class; the gate can't be unit-tested or audited in isolation |
| New state fields `website_search_results` / `discovery_search_results` / `official_gate_results` | spec writes `state.*` for the Step-4 handoff and offline evaluation (lines 486, 494–499) | STEP 4 has no URL to read; gate/search quality can't be evaluated after a run |
| New `WebsiteSelectionResult` + strict schema | selection must return a candidate-id/`none`, never a URL (anti-hallucination, lines 490–493) | the LLM can emit a fabricated URL that becomes `website_url` and feeds a nonexistent host to the crawl |
| Reuse `discovery_sem` bound (= `SEARCH_CONCURRENCY`) | many declined items fan out at once (lines 505–512) | the fan-out floods the Parallel pool and self-induces 429s |

**D. Kept concrete / rejected**

| Considered | Decision | Reason |
|---|---|---|
| A `WebsiteDiscovery`/`DiscoveryService` class for the mechanism | rejected | one responsibility class owns it; no second consumer, no state to encapsulate (over-engineering guard; user rule "no classes for mechanisms") |
| An abstraction/interface over the gate | rejected | exactly one implementation, no stated second; pure function suffices |
| R3.M1.2 result-shaping in discovery | rejected | not a dependency of R3.M1.3 (mermaid `s314 ↛ s315`); gateway returns typed `WebSearchResult \| ToolFailure` directly |
| A new gateway op / new MCP tool | rejected | discovery uses the existing `search_web`; map/scrape are phase-2 only |
| Crawl cache / single-flight across duplicate places | rejected | D4 revised — each work item discovers independently (spec line 501) |
| New exception subclass for discovery | rejected | failures degrade to `none` (D5); catalog reuses `MetricResolutionValidationError`, provider reuses `MetricResolutionProviderError` |
| Put discovery stores on a workflow-local object | rejected | spec explicitly says `state.*`, and the telemetry must outlive the run for evaluation |

### Layer 3 — Wiring
- **E. Dependency direction:**
  ```
  SpecificMetricResolution → [ToolGateway]            ← McpToolGateway / fake
  SpecificMetricResolution → StructuredLLMCaller      → OpenAI → Groq
  SpecificMetricResolution → build_tool_catalog / guard_proposed_calls   (R3.M1.1)
  SpecificMetricResolution → official_url_gate        → TLDExtract (offline PSL)
  SpecificMetricResolution → website_discovery_instruction
  ```
- **F. Composition root:** `create_specific_metric_resolution(settings, llm_caller=...)`
  ([specific_metric_resolution.py:78](../specific_metric_resolution.py))
  — unchanged; injects the gateway + resolves caller ownership. The gate's `TLDExtract` is a
  **module-level singleton** built once at import with the vendored PSL (its own tiny offline
  composition); `DISCOVERY_CONCURRENCY` is a module constant alongside the gateway's `SEARCH_CONCURRENCY`.
- **G. End-to-end flow:** `run_specific_metric_resolution(state)` → `gateway.open()` + capture
  `raw_tool_definitions` → `_build_plan_index` → `_derive_work_items` → `_run_discovery_batch`
  (`_discovery_pre_pass` gates all; declined fan out through `_discover_website_url` → search +
  selection; merge after the barrier) → `gateway.aclose()` → return `state` with the three discovery
  stores populated (STEP 4–6 not run).

### Layer 4 — Backing (why these wirings)
- The gate is a **module-level singleton** because `TLDExtract` loads the PSL once; rebuilding it per
  call re-reads the snapshot for a deterministic no-op. Offline (`suffix_list_urls=[]`) makes tests
  reproducible and the run network-free.
- Discovery stages are **methods on the responsibility class** (not a new class) because they need
  the injected `_tool_gateway` + `_llm_caller` and R3.M1.4/M1.5 will add sibling methods on the same
  class — the class is the responsibility's workflow owner, per the feature's Feature → Responsibility
  → Mechanism → Stage hierarchy. R3.M1.1 stays module functions because it is reused across contexts
  and holds no state; the gate follows that same "pure, reusable, module function" shape.
- **Return-then-merge** over in-task store writes keeps per-amenity isolation literal and removes any
  ordering assumption between concurrent tasks.

---

## Verification
1. **Unit/fixtures:** from `backend/`, `python -m pytest
   src/services/deep_search/feature_tests/test_r3_m1_3_website_url_discovery.py -q` — gate verdicts,
   id-indirection, retries, RC7/RC8, degrade-to-`none`.
2. **Live sample runner:** from `backend/`, `python -m
   src.services.deep_search.feature_sample_runs.r3_m1_3_website_url_discovery_sample_run` — one
   gate-`official` item (no search) and one declined item through a real search + selection; confirm
   `website_search_results`, `discovery_search_results`, `official_gate_results` print correctly and
   exit code 0.
3. **Regression:** run the existing R3.M1.1 and C3.1.1/C3.1.2 tests to confirm the schema + state
   additions don't disturb them: from `backend/`, `python -m pytest
   src/services/deep_search/feature_tests -q`.

## Build checklist (the `todos`)
1. `requirements.txt`: add pinned `tldextract`; vendor offline PSL snapshot under the package.
2. `schemas.py`: add the 4 discovery contracts + `WebsiteSelectionResult` wire model +
   `website_selection_json_schema()` + `WEBSITE_SELECTION_SCHEMA_NAME`; add the 3 `AmenitySearchState` fields.
3. `official_url_gate.py`: offline `TLDExtract`, `DENYLIST`, `compact`/`_match`, `official_url_gate` +
   `GateOutcome`; logging.
4. `feature_prompts/website_discovery_instruction.py`: `build_discovery_search_instruction` +
   `build_website_selection_instruction`.
5. `specific_metric_resolution.py`: `run_specific_metric_resolution` to STEP 3; `_build_plan_index`,
   `_derive_work_items`, `_run_discovery_batch`, `_discovery_pre_pass`, `_discover_website_url`,
   `_run_discovery_search`, `_select_candidate`, `_index_candidates`, `_resolve_verdict`;
   drift handling + logs + `DISCOVERY_CONCURRENCY`.
6. `feature_tests/test_r3_m1_3_website_url_discovery.py`: dummy-provider + gate unit tests (§4.2).
7. `feature_sample_runs/r3_m1_3_website_url_discovery_sample_run.py`: live stage-by-stage runner (§4.1).
