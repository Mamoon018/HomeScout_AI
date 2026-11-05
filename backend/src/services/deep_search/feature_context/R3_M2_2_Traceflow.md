# R3.M2.2 — Detailed Traceflow (Resolution Turn), with R3.M2.1

## Context

**Why this document exists.** R3.M2.2 runs the resolution call for one amenity. It depends on
R3.M2.1 for three things: the strict schema, the static instruction, and the input renderer. The
spec ([R3_Specific_Metric_Resolution_spec.md](R3_Specific_Metric_Resolution_spec.md)) and the
R3.M2.1 plan ([R3_M2_1_Resolution_Schema_Instruction_Implementation_Plan.md](R3_M2_1_Resolution_Schema_Instruction_Implementation_Plan.md))
describe them separately. This traceflow shows how they connect at runtime, box by box.

**Goal.** (1) Show how R3.M2.2 works step by step. (2) Mark, at every step, whether a decision
already covers it (✅ decided) or not (⚠ open). Part 4 collects the open points.

> This is an understanding artifact. It is derived from the spec and the R3.M2.1 plan. It does
> not change either.

**Legend**

```
┌─ BOX ─┐   one step, with its   in:  (what it reads)   and   out:  (what it produces)
✅          a decision in the spec or plan covers this point (pointer given)
⚠           no decision covers this point yet (listed in Part 4)
── ▶        data flows to the next step
```

---

## Part 1 — Where R3.M2.2 sits (the spine)

```
run_specific_metric_resolution(state)                                     [R3.M1.5]
│
├─ STEP 3  discovery batch → website_search_results                       [R3.M1.3]
│
├─ STEP 4  AMENITY PIPELINES (gather, one task per amenity)               [R3.M1.5]
│          _run_amenity_pipeline(work_item, rec, website, ...)
│          │
│          ├─ rec is None → pipeline_error, stop (R3.M2.2 never runs)    ✅ code precondition
│          ├─ phase1_loop → Phase1Result{metrics_source_content, ...}   [R3.M1.4]
│          │     provider failure → amenity ends, resolution_call_failed  ✅ R3.M1.4
│          │
│          ├─ ★ R3.M2.2  resolution (Part 3)                              ◀── this document
│          │       uses R3.M2.1 schema + instruction + renderer (Part 2)
│          │
│          └─ R3.M2.3 conform → R3.M2.4 provenance                        [later]
│
├─ STEP 5  post-gather sweep                                              [R3.M1.5]
└─ STEP 6  R3.M2.5 combine → state.amenity_records                        [later]
```

Triage and phase 2 are DEFERRED (spec scope 2026-11-02). R3.M2.2 reads phase-1 evidence only.

---

## Part 2 — R3.M2.1 building blocks (built once, used by every call)

```
┌─ R3.M2.1-A  resolution_json_schema() ───────────────────────────── once per run ─┐
│  in:  wire models MetricResolutionResult / MetricResolutionEntry /               │
│       ResolutionEvidenceEntry  (feature_schemas/schemas.py)                       │
│  do:  model_json_schema() → _apply_strict_object_rules                            │
│       (all keys required, objects closed, enums closed, final_value = anyOf)      │
│  out: schema : dict                                                               │
│  ✅ Approach 2 static schema (spec R3.M2.1; plan §2 F)                            │
└───────────────────────────────────────────────────────────────────────────────────┘
        │ schema
        ▼
┌─ R3.M2.1-B  build_resolution_instruction(schema) ───────────────── once per run ─┐
│  in:  schema                                                                      │
│  do:  join fixed sections in order:                                               │
│       task → input layout → evidence source rules → decision procedure 1-9 →      │
│       source-value fields → relation & basis → mixed opinion → final_value        │
│       format → evidence quotes → untrusted-content rule → output rules            │
│       (one entry per listed metric) → schema JSON → 2 worked pairs                │
│  out: instruction : str   (identical for every amenity → cacheable)               │
│  ✅ plan §2 D "Instruction sections"                                              │
│  ⚠ G4  where it is built and held (per run / per pipeline) is not stated in spec  │
└───────────────────────────────────────────────────────────────────────────────────┘

┌─ R3.M2.1-C  render_resolution_input(name, address, website_url, metrics, store) ─┐
│  (called per call by R3.M2.2 Step 3 — shown here because R3.M2.1 owns it)         │
│  in:  rec.name, rec.address, website.website_url, MetricSpec[] (all or subset),   │
│       metrics_source_content                                                      │
│  do:  amenity{name|"(unavailable)", address|"(unavailable)", website_url|"none"}  │
│       metrics[] in given order; each = spec fields + evidence[{source,url,text}]  │
│         from store.items_for(label); empty bucket → evidence: []  (never omitted) │
│       google_reviews = {text} from the google_reviews item, or null               │
│       no evidence_id, no retrieved_at; json.dumps(indent=2, ensure_ascii=False)   │
│  out: user_turn : str (JSON)                                                      │
│  ✅ plan §2 B contract rules, §2 E pointers                                       │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 3 — R3.M2.2 per amenity, step by step

```
 in:  rec : PredefinedMetricsRecord          (name, address, reviews)
      website : WebsiteSearchResult          (website_url | None)
      work_item.specific_metrics : MetricSpec[]   (the submitted labels)
      phase1.metrics_source_content : store  (web items only)
      phase1.metric_outcomes / uncovered_labels
      schema, instruction                    (Part 2, built once)
      breaker, run_id, key
        │
        ▼
┌─ STEP 1  _record_review_evidence(rec, store, retrieved_at) ──────────────────────┐
│  in:  rec.reviews (≤ 5 Google reviews), store                                     │
│  do:  keep reviews that have text (text.text, else original_text.text)            │
│       format: "Review 1 (★3): <text>" ⏎⏎ "Review 2 (★5): <text>" ...             │
│         rating → whole number; missing rating → "Review N:"                       │
│         author, photo, links, publish time left out                               │
│       store.record("google_reviews", url=None, shaped_text, retrieved_at,         │
│                    metric_label=None)   → metric_labels stays empty               │
│  out: store + 0 or 1 google_reviews item                                          │
│       nothing written when reviews None / empty / no review has text             │
│  ✅ spec R3.M2.2 "Reviews item" (input, format, retrieved_at, when nothing)       │
└───────────────────────────────────────────────────────────────────────────────────┘
        │ store
        ▼
┌─ STEP 2  Skip rule (structural gate) ─────────────────────────────────────────────┐
│  in:  store, submitted labels                                                     │
│  do:  has_metric_evidence = any label with store.items_for(label) non-empty       │
│       has_reviews        = a google_reviews item exists                           │
│  out: ├── neither ──▶ every metric unresolved(no_evidence) ──▶ hand-off (Step 5)  │
│       └── either  ──▶ Step 3                                                      │
│  ✅ spec R3.M2.2 "Skip rule"  (never reads verification text)                    │
└───────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ STEP 3  CALL 1 — fresh resolution call ──────────────────────── call 1 of max 2 ─┐
│  in:  instruction (system), all submitted MetricSpec[], store, identity           │
│  do:  user_turn = render_resolution_input(... all metrics ...)    [R3.M2.1-C]     │
│       breaker check first → open → ProviderError(cause=circuit_open)              │
│       call_structured(instruction, user_turn, schema,                             │
│                       RESOLUTION_SCHEMA_NAME, stage, MetricResolutionProviderError)│
│         OpenAI → Groq chain; strict mode; refusal / truncation / content_filter   │
│         → fallback to the next provider                                           │
│  out: ├── body : dict ──▶ Step 4                                                  │
│       └── MetricResolutionProviderError ──▶ ALL metrics                           │
│              unresolved(resolution_call_failed) ──▶ hand-off (Step 5)             │
│  ✅ spec R3.M2.2 "Resolution input", "Failure result"; spec line 177 strict mode  │
│  ⚠ G5  the stage name used for call 1 vs the follow-up is not stated              │
└───────────────────────────────────────────────────────────────────────────────────┘
        │ body
        ▼
┌─ STEP 4  Parse + label coverage ──────────────────────────────────────────────────┐
│  4a  PARSE                                                                        │
│      MetricResolutionResult.model_validate(body)                                  │
│      fails → no retry, no fallback (chain already finished) →                     │
│              that call's metrics unresolved(resolution_call_failed)               │
│      ✅ spec R3.M2.2 "Unparseable body"; line 177                                 │
│                                                                                   │
│  4b  SORT EACH RETURNED ENTRY BY LABEL                                            │
│      ┌──────────────┬──────────────────────────────┬───────────────────────────┐  │
│      │ Correct      │ submitted, appears once      │ KEEP → kept{}             │  │
│      │ Extra        │ never submitted              │ DROP (log extra_label_    │  │
│      │              │                              │       dropped)            │  │
│      │ Duplicate    │ submitted, appears >1        │ DROP all copies → missing │  │
│      │              │                              │ (log duplicate_label)     │  │
│      │ Missing      │ submitted, not returned      │ → missing[]               │  │
│      └──────────────┴──────────────────────────────┴───────────────────────────┘  │
│      log metric_resolution.validated (kept / dropped / missing counts)            │
│      ✅ spec R3.M2.2 "Label coverage" Step 1; LC3 (never counts to breaker)       │
│                                                                                   │
│  out: ├── missing empty ──▶ hand-off (Step 5)                                     │
│       └── missing non-empty ──▶ 4c                                                │
│                                                                                   │
│  4c  FOLLOW-UP (CALL 2) — missing labels only ──────────────── call 2 of max 2    │
│      skip rule on the missing metrics first:                                      │
│        none has evidence AND no reviews → unresolved(no_evidence), no call        │
│      else: log missing_label_retry(labels)                                        │
│        user_turn = render_resolution_input(... missing MetricSpecs only ...)      │
│        breaker check → call_structured (same instruction + schema)                │
│        ProviderError  → missing labels unresolved(resolution_call_failed);        │
│                         kept{} stands                                             │
│        parse fails    → missing labels unresolved(resolution_call_failed)         │
│        parse ok       → sort with 4b rules; correct entries merged into kept{}    │
│                         (kept entries never re-asked or overwritten)              │
│      still missing    → unresolved(resolution_body_invalid);                      │
│                         log metric_resolution.rejected                            │
│      no third call (LC2: follow-up always sent when labels are missing)           │
│      ✅ spec R3.M2.2 "Label coverage" Steps 2-3; LC1, LC2; D2 = max 2 calls       │
└───────────────────────────────────────────────────────────────────────────────────┘
        │ kept{}, unresolved{}
        ▼
┌─ STEP 5  R3.M2.2 output = amenity pipeline output ────────────────────────────────┐
│  in:  kept : label → MetricResolutionEntry                                        │
│       unresolved : label → reason (no_evidence | resolution_call_failed |         │
│                                    resolution_body_invalid)                       │
│       store (R3.M2.4 checks quotes against it)                                    │
│  out: every submitted label is in exactly one of kept / unresolved                │
│       this object is what R3.M2.2 returns AND what _run_amenity_pipeline returns  │
│       (replaces the temporary AmenityPhase1Record) ──▶ STEP 4 gather              │
│       kept ──▶ R3.M2.3 conform + verification gate ──▶ R3.M2.4 provenance (later) │
│  ✅ G2/G3 decided: R3.M2.2 output is the amenity pipeline output                  │
│  ⚠ G2a  its class name and fields are not yet written into the spec              │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Call budget per amenity (D2)

```
 Skip rule hit ...................................... 0 calls
 Call 1 complete (all labels correct) ............... 1 call
 Call 1 provider failure / unparseable .............. 1 call   (no re-ask)
 Call 1 missing labels, follow-up skipped (no ev.) .. 1 call
 Call 1 missing labels → follow-up .................. 2 calls  (ceiling)
```

---

## Part 4 — Decision coverage check

| Step | Point | Status | Where |
| --- | --- | --- | --- |
| R3.M2.1-A | Static strict schema, typed-union `final_value` | ✅ | spec R3.M2.1, plan §2 F |
| R3.M2.1-B | Instruction content and order | ✅ | plan §2 D |
| R3.M2.1-B | Where the instruction/schema are built and held | ⚠ G4 | not in spec |
| R3.M2.1-C | Input layout, placeholders, empty buckets listed | ✅ | plan §2 B, §2 E |
| 1 | Reviews item: input, format, `retrieved_at`, empty cases | ✅ | spec "Reviews item" |
| 2 | Skip rule | ✅ | spec "Skip rule" |
| 3 | Fresh call, system + user turn, no tools | ✅ | spec "Resolution input" |
| 3 | Provider failure / breaker / refusal | ✅ | spec "Failure result", line 177 |
| 3 | `stage` names for call 1 and the follow-up | ⚠ G5 | not in spec |
| 4a | Unparseable body | ✅ | spec "Unparseable body" |
| 4b | Correct / extra / duplicate / missing | ✅ | spec "Label coverage" Step 1 |
| 4c | Follow-up, skip on subset, merge, final reason | ✅ | spec "Label coverage" Steps 2-3, LC1-LC3 |
| 4c | Max 2 calls per amenity | ✅ | spec Step 3 (D2) |
| — | Logging events | ✅ | spec "Logging" |
| 5 | R3.M2.2 output is the amenity pipeline output (G2 + G3) | ✅ | user decision (2026-11-03) |
| 5 | Class name and fields of that output | ⚠ G2a | not in spec |

### Open points

| ID | Open point | Why it matters | Suggested owner |
| --- | --- | --- | --- |
| G2a | Name and fields of the R3.M2.2 / pipeline output (kept entries, unresolved reasons, store, amenity key, outcome). | The STEP 4 gather, the STEP 5 sweep and R3.M2.3 all read it. | R3.M2.2 spec |
| G4 | Where are the schema and instruction built (once per run, held on the class)? | It decides whether the text is built once or per amenity. | Safe default: once per run |
| G5 | `stage` names for call 1 and the follow-up | Logs and `MetricResolutionProviderError.stage` should tell them apart. | Safe default: `resolution` / `resolution_followup` |

### Small spec note

The spec's "Reviews item" says nothing is written when `rec` is None. That case never reaches
R3.M2.2: `_run_amenity_pipeline` returns `pipeline_error` before phase 1 when `rec` is None.
