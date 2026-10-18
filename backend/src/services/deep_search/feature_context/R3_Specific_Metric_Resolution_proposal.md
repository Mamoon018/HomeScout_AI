# R3 — Specific Metric Resolution: Responsibility-Promotion Proposal

> **Status: INITIAL SPEC FOR PLANNING.** This promotes the work currently written as
> "R2 Mechanism 3" into its own responsibility class. It is the agreed structural target;
> the implementation plan will be built on top of it. The finalized sub-component specs in
> `R2_Mechanism_3_draft_spec.md` are **not** re-authored here — this document defines where
> they live, how they are numbered, and what moves in the code and the context doc.

---

## 0. Numbering convention (agreed)

The new responsibility is labelled **R3 (Specific Metric Resolution)**. Candidate-selection /
narrowing is **not** treated as a responsibility in the current model, so no slot is reserved
for it — the feature's responsibilities are R1, R2, R3. Execution order is **R1 → R2 → R3**.

---

## 1. Decisions carried into this proposal

| # | Decision | Source |
|---|---|---|
| D-A | Promote "R2 Mechanism 3" to its own responsibility **class**, `SpecificMetricResolution`. | agreed |
| D-B | Label it **R3**; candidate-selection is not treated as a responsibility in the current model. | your reply |
| D-C | Name reflects scope precisely — it resolves **`specific_metrics`**, not all metrics. File `specific_metric_resolution.py`. | your reply |
| D-D | Re-slice R2's problem context (User / Environment / Problem Statement) so R3's frame is carved out of R2's and both stay symmetric in the context doc. | your reply |
| D-E | The combined, versioned **`AmenityMetricsSet` is produced inside R3** (C3.2.5 stays in R3). | your reply (recommendation rejected) |
| D-F | Gateway ownership + lifecycle move to R3's factory; **shared LLM caller stays owned by `DeepSearch`**, injected into R1 and R3. Do not strip the caller from `AmenitySearch` yet (R2's unbuilt relevance/narrowing may need it). | your reply |
| D-G | Keep a **single shared `AmenitySearchState`** threaded by the coordinator; document R3's read/write surface; no premature state split. | your reply |
| D-H | **One class per responsibility.** Mechanisms are workflows (grouped stage methods), never their own classes. | your structure rule |
| D-I | **Entry-method name decided:** `run_specific_metric_resolution(state)` — consistent with R2's `run_*` convention. | your reply |

**Why R3 is a responsibility, not a mechanism.** What the draft calls "M3" already decomposes
into two complete mechanism workflows — C3.1 (Evidence Acquisition) and C3.2 (Resolution) — each
with its own stage methods. Under the structure rule (feature → responsibility → *mechanism
workflows* → stage methods), a unit that **owns two mechanisms is a responsibility**. That, not
just its distinct dependencies, is why it is eligible for promotion.

---

## 2. R3 identity and boundary

**Responsibility (one line):** resolve each LLM-defined `specific_metric` of each eligible
amenity to a committed, verified, provenance-checked factual value (or an honest unresolved
reason), and assemble the combined versioned amenity metrics set.

**R3 does:** website resolution → multi-source evidence acquisition (web search, then scrape)
→ per-metric resolution, verification, conformance, provenance → combine into `AmenityMetricsSet`.

**R3 does not:** interpret requirements (R1); discover, profile, relevance-filter or narrow
amenities (R2); score or assess amenities (the later responsibility).

### Contract

| Boundary | Contract |
|---|---|
| **Input** | R1's `specific_metrics` plans (via `CategoryMetricPlan`); R2's `state.discovered_places`; R2's `state.predefined_records` (website candidate for discovery, and the predefined half of the combine). |
| **Output** | Per-amenity `SpecificMetricsRecord` → `state.specific_records`; the combined, versioned `AmenityMetricsSet` (contract 1.0) → `state.amenity_records`. |
| **Dependencies** | **MCP tool gateway** (owned by R3; session opened/closed inside R3's entry method; its Firecrawl token bucket is **gateway-instance** state — the gateway R3 owns, so one gateway paces all of R3's concurrent amenities). **Shared `StructuredLLMCaller`** (injected, owned by `DeepSearch`). |
| **Coordination** | `DeepSearch` invokes R3 after R2's attachment. R3 runs its two mechanisms internally; the coordinator calls a single R3 entry method. |

**One accepted asymmetry (consequence of D-E).** Because the combine lives in R3, R3 reaches
into R2's output (`predefined_records`) to assemble the final `AmenityMetricsSet`. This is on
the record as deliberate: R3's Resolution mechanism owns the terminal assembly stage, so R3's
output surface is both its own `specific_records` *and* the feature's combined set.

---

## 3. Re-slicing R2's problem context into R3 (D-D)

The context doc frames R2 as a single responsibility whose problem statement explicitly claims
factual resolution (`deep_search_context.md:2185`). Promotion migrates the **unstructured /
LLM-defined** half of that frame to R3 and trims R2 to finding + baseline profiling. The split
below is the source for the context-doc rewrite; it keeps each section symmetric across R2 and R3.

### Customer wants

| Want | R2 keeps | R3 takes |
|---|---|---|
| Correct-Category Results | ✅ | — |
| Non-Redundant Set (narrowing) | ✅ (not yet built) | — |
| Metric-Level Factual Correctness | predefined facet | **LLM-defined facet** |
| Data-Point Completeness | predefined facet | **specific facet (unit/scale/link)** |
| Honest Absence | predefined null | **specific unresolved-reason machinery** |
| Currency of Facts | predefined as-of | **tool-evidence `retrieved_at` / `as_of`** |
| Display-Ready Structure | baseline record shape | **combined versioned set assembly** |

### Developer wants

| Want | R2 keeps | R3 takes |
|---|---|---|
| Relevance Filtering Criteria | ✅ | — |
| Efficient Parsing of Structured Returns | ✅ (Google fields) | — |
| Source-Appropriate Routing | structured path | **unstructured path (web/scrape)** |
| Cost-Bounded Extraction | — | **tool spend / bounded loops** |
| Low-Latency Extraction | Google-call latency | tool-loop latency |
| Controlled Parallelism | Places/Routes semaphores | gateway semaphores + per-amenity scrape ceiling |
| Mergeable Output | baseline record | **owns the merge (D-E)** |

### Environment facts

| Fact | Home |
|---|---|
| Search APIs rank by proximity → irrelevance is inherent | R2 |
| User-defined radius; uneven amenity density | R2 |
| Travel-based accessibility is layered on coordinates | R2 |
| Spec is pre-split predefined / LLM-defined (routing basis) | **shared** — structured half R2, LLM-defined half R3 |
| Not every value is published anywhere retrievable | **R3** |
| LLM-defined metrics have no structured source (free-text assembly) | **R3** |
| Cost/latency compound across amenities × categories × metrics in one run | **R3** |
| Each tool has its own rate limits / coverage boundary | **R3** (MCP tools) |
| Facts change over time → value correct as-of fetch | **R3** |

### Drafted R3 Scope Boundary (for the context doc)

> R3 consumes R2's discovered places and baseline `PredefinedMetricsRecord`s plus R1's
> `specific_metrics` plans. It resolves the LLM-defined metrics from live web-search and scrape
> evidence (with Google reviews as a verification-gated fallback), commits a verified value or an
> honest unresolved reason per metric, and assembles the combined versioned `AmenityMetricsSet`.
> It does not find, profile, filter, or narrow amenities (R2), and it does not score them (later).

### Drafted R3 Actual Problem Statement (for the context doc)

> Taking the per-category specification's LLM-defined `specific_metrics`, the discovered amenity
> set, and the baseline `PredefinedMetricsRecord`s produced by Responsibility-2 as its input,
> this responsibility resolves each LLM-defined metric to a committed factual value. For each
> eligible amenity (a category with ≥1 `specific_metrics` entry) it must first resolve the
> amenity's official website, then acquire evidence through the tools each metric's
> `resolution_source` dictates — Parallel web search first, Firecrawl page scraping for what web
> search leaves unresolved — deciding per metric when the cheaper source suffices so scraping
> cost is incurred only where it adds value. It must then commit, per metric, the true
> as-of-fetch-time value complete with unit and scale, verified against that metric's
> verification rule, conformed to its value type and enum, and provenance-checked against the
> evidence actually retrieved; where no source yields a verifiable value it must mark the metric
> unresolved with a reason rather than fabricate one. Finally it must assemble its per-amenity
> specific records together with Responsibility-2's predefined records into the single versioned
> `AmenityMetricsSet`, organized by category and metric, ready for downstream null-policy
> application and assessment. It operates within cost and latency bounds using bounded
> parallelism across independent amenities and metrics, and produces factual values only — it
> performs no requirement interpretation (R1), no amenity discovery or baseline profiling (R2),
> no candidate narrowing, and no scoring or assessment (the later responsibility).

### Trimmed R2 boundary (what R2 is reduced to)

R2 = **Amenity Discovery & Baseline Profiling**: search each category, filter to correct-category
members, retrieve predefined/baseline metrics by parsing structured Google fields, compute
travel-based accessibility, narrow to a representative set, and emit one `PredefinedMetricsRecord`
per amenity per category. The "resolve the deeper LLM-defined metrics…" and "assemble into one
merge-ready record…" clauses leave R2's statement and move to R3.

---

## 4. Internal structure of R3 (D-H)

**One class, two mechanism workflows, stage methods derived from them.**

```
Feature: DeepSearch (coordinator)
  └─ Responsibility R3: SpecificMetricResolution      ← the only class R3 introduces
       entry: run_specific_metric_resolution(state)
         │
         ├─ Mechanism 1 — Evidence Acquisition   (was C3.1)
         │     stages: plan work items · resolve website (discovery batch) ·
         │             build tool catalog · guard proposed calls · shape tool results ·
         │             phase-1 loop / triage / phase-2 loop · run amenity pipeline
         │
         └─ Mechanism 2 — Resolution             (was C3.2)
               stages: resolution turn + body validation · conform + verification gate ·
                       provenance verification · combine → write AmenityMetricsSet
```

**Collaborators that stay as clients, not R3 stages (and are already built):**

- **MCP tool gateway** — `src/clients/mcp_tools.py` (current `C3.1.1`). An infrastructure client
  (peer of `GooglePlacesAsyncClient`), injected into R3. Its methods are *not* R3 stage methods.
- **Tool-turn on the shared caller** — `src/clients/llm_provider.py` (current `C3.1.2`). Part of
  the shared `StructuredLLMCaller`, injected. Not an R3 stage.

This is the key point for D-H: `mcp_tools` and `llm_provider` are **clients**, not
"mechanism-as-class." No mechanism of R3 becomes a class — the two mechanisms are groups of stage
methods on the single `SpecificMetricResolution` class, exactly as R1's mechanisms are methods on
`UserRequirementsInterpretation` and R2's are methods on `AmenitySearch`.

**Entry-method nuance.** Unlike R2's Mechanism 1, whose components can be sequenced by the
coordinator as separate `run_*` calls, R3's two mechanisms **interleave per amenity** (each
pipeline runs evidence acquisition then resolution for that amenity before the next). So R3
exposes a **single** entry method, `run_specific_metric_resolution(state)` (decided, D-I —
consistent with `run_place_discovery` / `run_accessibility_enrichment` / `run_result_attachment`),
and drives both mechanisms internally — consistent with the draft's `C3.1.7` orchestration.

---

## 5. Numbering crosswalk (C3.x → R3)

Target IDs for the context doc and the renamed spec. Executing the ID rename across the finalized
sub-component text is a mechanical **plan step**, not done here.

| Current (draft) | Target | Home |
|---|---|---|
| C3.1.1 MCP gateway | — (client prereq) | `src/clients/mcp_tools.py` — already built |
| C3.1.2 tool turn on caller | — (client prereq) | `src/clients/llm_provider.py` — already built |
| C3.1.3 tool catalog + call guard | **R3.M1.1** | R3 stages/helpers |
| C3.1.4 shape tool results | **R3.M1.2** | R3 stage |
| C3.1.5 website URL resolution | **R3.M1.3** | R3 stage (discovery batch) |
| C3.1.6 phase loop + triage | **R3.M1.4** | R3 stages |
| C3.1.7 work items + pipelines | **R3.M1.5** | R3 entry + orchestration |
| C3.2.1 schema + instruction | **R3.M2.1** | `feature_prompts/` + `feature_schemas/` (modules, not a class) |
| C3.2.2 resolution turn + validation | **R3.M2.2** | R3 stage |
| C3.2.3 conform + verification gate | **R3.M2.3** | R3 stage |
| C3.2.4 provenance verification | **R3.M2.4** | R3 stage |
| C3.2.5 combine + record write | **R3.M2.5** | R3 stage (owns `AmenityMetricsSet`, D-E) |

---

## 6. Code change map

| File | Change |
|---|---|
| `deep_search/specific_metric_resolution.py` | **New.** `SpecificMetricResolution` class + `create_specific_metric_resolution(settings, *, llm_caller)` factory. Holds R3's two mechanisms' stage methods; owns the gateway lifecycle (`open()` at entry, `aclose()` at teardown). |
| `deep_search/feature_prompts/specific_metric_resolution_instruction.py` | **New** (R3.M2.1 instruction builder, per existing instruction-module pattern). |
| `deep_search/feature_schemas/schemas.py` | **No new record types.** The RC9 contracts already exist and are correctly shaped: `PredefinedMetricsRecord`, `ResolvedMetric`, `SpecificMetricsRecord`, `AmenityMetricsRecord`, `AmenityMetricsSet`, `AMENITY_METRICS_CONTRACT_VERSION`, `state.specific_records`, and `state.amenity_records: AmenityMetricsSet \| None` (`AmenityRecordSet` already removed, rename already applied). Cross-checked against the live file: `ResolvedMetric`, `EvidenceItem`, `SpecificMetricsRecord`, `AmenityMetricsRecord`, and `AmenityMetricsSet` already match the draft C3.2.5 field lists — **nothing to add or change**. The one genuinely new schema asset is the resolution-turn JSON schema (R3.M2.1), authored as a prompt/schema asset below, not a record type. |
| `deep_search/amenity_search.py` | Remove `tool_gateway` param, the M3 comments, the gateway build in `create_amenity_search`, and the gateway branch in `aclose()`. **Keep** `llm_caller`/`owns_caller` (D-F). |
| `deep_search/deep_search.py` | `create_deep_search` builds R3 via `create_specific_metric_resolution(settings, llm_caller=llm_caller)`; inject into the feature; `run()` sequences R1 → R2 → R3; `aclose()` closes R1, R2, R3, then the shared caller. |
| `clients/mcp_tools.py`, `clients/llm_provider.py` | Unchanged by the split (already built; now injected into R3 instead of R2). |

**Low risk:** R2 is not wired into `DeepSearch.run()` today (it only runs R1), so moving M3 out
reshapes no live call graph — the R2+R3 coordinator wiring is greenfield.

---

## 7. Context-doc / spec-doc change map

| Doc | Change |
|---|---|
| `R2_Mechanism_3_draft_spec.md` | Rename/retitle to the R3 spec; apply the §5 ID crosswalk; retarget every "on/into `AmenitySearch`" binding (test seam, placement, wiring, factory) to `SpecificMetricResolution`. |
| `deep_search_context.md` — R2 section | Trim R2 to §3's "Trimmed R2 boundary"; drop the LLM-defined-resolution and merge clauses from R2's problem statement; update "R2 is its own class" framing (`:2240`) — it no longer owns metric resolution. |
| `deep_search_context.md` — new R3 section | Add a symmetric responsibility section (Scope, User, Environment, Problem relevance, Actual Problem Statement, Workflow, Mechanisms) seeded from §3's drafts, mirroring R1/R2 structure. |
| `deep_search_context.md` — feature coordination | Note the feature sequences R1 → R2 → R3 and that R3 owns the combined `AmenityMetricsSet`. |

---

## 8. Open items for the plan

**Entry-method name — decided (D-I):** `run_specific_metric_resolution(state)`.

The items below remain open and are **now recorded as open decisions in the specs themselves**
(`R2_Mechanism_3_draft_spec.md` and `deep_search_context.md`), each at/next to its sub-component,
so they persist beyond this proposal:

1. **C3.1.5 postal-code degrade path** — injected vs instructed; carried forward, unaffected by the split.
2. **C3.2.2 / C3.2.3 / C3.2.4 sub-decisions** — body-validation, conformer, and provenance-match
   approaches remain open; the split does not close them.
3. **ID-rename execution** — mechanical sweep of the finalized sub-component text to the §5 IDs
   (`R3.M1.x` / `R3.M2.x`), sequenced before implementation so references stay consistent.

---

## 9. Regression surface — tests to re-run

The promotion's one breaking change for other responsibilities is the **`AmenitySearch.__init__`
signature** (removing `tool_gateway`). The breaks are at **construction only** — the behaviour
under test is untouched, so each is a one-line fix (drop the `tool_gateway` kwarg) followed by a
re-run.

**Breaks — all R2 Mechanism-1 tests (a different responsibility):**

| Test file | Covers | Fix |
|---|---|---|
| `backend/tests/services/deep_search/test_place_discovery.py` | R2 M1.1 | drop `tool_gateway` kwarg, re-run |
| `backend/tests/services/deep_search/test_accessibility_enrichment.py` | R2 M1.2 | drop `tool_gateway` kwarg, re-run |
| `backend/tests/services/deep_search/test_result_attachment.py` | R2 M1.3 | drop `tool_gateway` kwarg, re-run |

**Also breaks the same way (not tests) — M1 sample runs:** `place_discovery_sample_run.py`,
`accessibility_enrichment_sample_run.py`, `result_attachment_sample_run.py`, and
`mcp_tool_gateway_sample_run.py` construct `AmenitySearch` the same way and need the same one-line fix.

**Unaffected (sanity re-run only):** the gateway and shared-caller tests
(`test_c3_1_1_mcp_tool_gateway.py` / `test_mcp_tool_gateway.py`, `test_c3_1_2_structured_llm_caller.py`)
test those units directly, not through `AmenitySearch`; only their injection target moves (R2 → R3).
R1 (`UserRequirementsInterpretation`) tests are unaffected — R1 only receives the shared caller,
which does not change.

**Gap, not a breakage:** there is **no** existing test for `create_deep_search` /
`DeepSearch.run()` / `aclose()`. The promotion rewires exactly that, but since R2 was never wired
into `run()` and nothing tests the coordinator, nothing breaks — this is where a **new** test
should land when the R1 → R2 → R3 wiring is built.
