# Responsibility 2 — Mechanism 1, Component M1.3 (Deterministic Result Attachment): Implementation Plan

Scope: **Component M1.3 (Deterministic Result Attachment and Output Contract)** and its three
sub-components only.
- M1.3.a Canonical Profile Projection
- M1.3.b Accessibility Unit Conversion
- M1.3.c Record Assembly, Join, and State Write

M1.1 (Place Discovery) and M1.2 (Accessibility Enrichment) are already built. M1.3 reads the
frozen `discovered_places` and the `enrichment` those wrote and produces the versioned
`amenity_records` envelope. Architecture and modularity decisions are combined at the end of this
file (not a separate file).

## Context

M1.3 is the final component of Mechanism 1. It joins the enrichment onto each discovered place by
`place_id`, normalizes units (meters to km, seconds to minutes), and assembles one typed
`AmenityRecord` per (category, place) into a single versioned envelope on the state. It is a pure
in-memory transform. It calls no external API and no LLM, so it adds no client, no provider, and no
prompt module.

Grounding from committed M1.1 / M1.2 code:
- `discovered_places` is `dict[category_id][place_id] -> CanonicalPlace`; `CanonicalPlace.place`
  is `Place.to_dict(...)`, a nested dict with proto snake_case keys (`display_name`,
  `formatted_address`, `user_rating_count`, `regular_opening_hours`, `international_phone_number`,
  `primary_type`, `google_maps_uri`, `reviews`, `location`, `website_uri`, `rating`,
  `price_level`).
- `enrichment` is `dict[place_id] -> EnrichmentBundle`; `routing` is `dict[mode] -> RouteLeg |
  None`, `transit` is `TransitLeg | None`; legs carry raw `distance_m` (int m) and `duration_s`
  (int s); `TransitLeg` also carries `used_fallback: bool`.
- `_METERS_PER_KM = 1000.0` exists in [amenity_search.py](../amenity_search.py); `ROUTING_MODES`,
  `DepthLevel`, and `GeoPoint` exist in [schemas.py](../feature_schemas/schemas.py).

---

## 1. File and Module Structure (Build todos)

No prompt module and no client change: M1.3 makes no LLM or API call.

| # | File | New/Modify | Purpose and ownership |
| --- | --- | --- | --- |
| 1 | `backend/src/services/deep_search/feature_schemas/schemas.py` | Modify | Add `AMENITY_RECORD_CONTRACT_VERSION`; `RouteView`, `TransitView` (frozen leaf views); `AmenityRecord` (frozen, all profile fields Optional, no `contract_version`); `AmenityRecordSet` (frozen envelope: `contract_version` + nested `records`). Add `amenity_records: AmenityRecordSet | None = None` to `AmenitySearchState`. |
| 2 | `backend/src/exceptions/deep_search.py` | Modify | Add the `ResultAttachmentError` tree: base (with `stage`) and `ResultAssemblyError` (stage `assemble_amenity_records`) for the join invariant. |
| 3 | `backend/src/services/deep_search/amenity_search.py` | Modify | Add M1.3 methods to `AmenitySearch`: `run_result_attachment`, `assemble_amenity_records`, `project_place_profile`, `convert_route_leg`, `convert_transit_leg`, `convert_accessibility`; a km/min conversion helper reusing `_METERS_PER_KM`; the completion log event constant. |
| 4 | `backend/src/services/deep_search/feature_sample_runs/result_attachment_sample_run.py` | New | Live, stage-by-stage runner over hand-built dummy state as after M1.2; runs the M1.3 stages in sequence; prints a titled section per stage; reads `homescout.places` records. No external call. |
| 5 | `backend/tests/services/deep_search/test_result_attachment.py` | New | Pure-transform pytest (no client, no live call): assert projection, conversion, join, envelope shape, and the assembly error. |

The live sample runner (file 4) is required by the plan format and is not part of the request path
in section E.

---

## 2. Implementation Architecture and Design Decisions

Combined at the end of this file under "Architecture and Modularity Decisions" (Layers 1 to 4,
dependency direction, composition root, async execution map, backing).

---

## A. Feature Map

```
Feature: Deep Search
└─ FeatureClass: (orchestrator, later): sequences the three responsibilities
   └─ Responsibility 2: AmenitySearch: find real amenities and collect their facts
      └─ Mechanism 1 Workflow (M1.3): run_result_attachment: enrichment + places -> versioned records
         ├─ Stage a: project_place_profile: raw place dict -> profile fields, null on missing (M1.3.a)
         ├─ Stage b: convert_accessibility (+ convert_route_leg / convert_transit_leg): legs -> km/min views (M1.3.b)
         └─ Stage c: assemble_amenity_records: pre-indexed join per (category, place) -> AmenityRecordSet (M1.3.c)
```

> M1.1 (`run_place_discovery`) and M1.2 (`run_accessibility_enrichment`) are earlier workflow
> methods on the same class; they write `discovered_places` and `enrichment`, which M1.3 reads.

## B. Data Contracts

| Contract | Purpose | Fields (`name: type - meaning`) | Mutability | Created by -> Read by |
| --- | --- | --- | --- | --- |
| `AmenityRecord` | one amenity per category | `category_id: int` · `taxonomy_node: str` · `depth: DepthLevel` · `place_id: str` · `name: str \| None` · `category: str \| None` · `address: str \| None` · `website: str \| None` · `google_maps_uri: str \| None` · `coordinates: GeoPoint \| None` · `opening_hours: dict \| None` · `contact_phone: str \| None` · `rating: float \| None` · `review_volume: int \| None` · `price_level: str \| None` · `reviews: list \| None` · `routing: dict[str, RouteView \| None]` · `transit: TransitView \| None` | immutable (frozen) | Stage c -> M2 |
| `RouteView` | one converted non-transit leg | `distance_km: float` · `duration_min: float` | immutable (frozen) | Stage b -> `AmenityRecord.routing` |
| `TransitView` | one converted transit leg | `distance_km: float` · `duration_min: float` · `used_fallback: bool` | immutable (frozen) | Stage b -> `AmenityRecord.transit` |
| `AmenityRecordSet` | the versioned envelope | `contract_version: str` · `records: dict[int, dict[str, AmenityRecord]]` | immutable (frozen) | Stage c -> state / M2 |
| `AmenitySearchState` (existing, extended) | R2 mutable handoff | add `amenity_records: AmenityRecordSet \| None = None` | **mutable**: M1.3 writes `amenity_records` | Stage c writes; reads `discovered_places`, `enrichment`, `category_metric_plans` |

> Rules to surface: version is stamped once on `AmenityRecordSet`, never per record; every profile
> field is `X | None` (null on missing, no fabricated default); `records` mirrors
> `discovered_places` keying (category_id then place_id); `routing` always carries every
> `ROUTING_MODES` key with `None` where absent; `coordinates` reuses the existing `GeoPoint`.

## C. Supporting Actors & Interfaces

| Actor | Kind | Contract (used capability) | Implementations | Depended on by |
| --- | --- | --- | --- | --- |
| `CanonicalPlace` (existing) | contract | `.place: dict` raw source for projection | one | Stage a |
| `EnrichmentBundle` (existing) | contract | `.routing: dict[mode, RouteLeg\|None]` · `.transit: TransitLeg\|None` | one | Stage b |
| `CategoryMetricPlan` (existing) | contract | `.depth`, `.taxonomy_node` by `category_id` | one | Stage c |
| `ROUTING_MODES`, `GeoPoint`, `DepthLevel`, `_METERS_PER_KM` (existing) | constants/types | fixed mode set, coordinate type, depth band, meters-per-km | one each | Stages a, b, c |
| `ResultAttachmentError` tree (new) | exceptions | `ResultAssemblyError` with `stage` | concrete | Stage c |

## D. Class & Method Blueprint

**`AmenitySearch`** (existing): add the M1.3 workflow entry and its stage methods. No new
constructor dependency; no async (see async map).

| Method | Signature | Purpose (one line) |
| --- | --- | --- |
| `run_result_attachment` | `(state: AmenitySearchState) -> AmenitySearchState [mutates: state.amenity_records] [raises: ResultAttachmentError]` | drive M1.3, write the versioned envelope, retain enrichment |
| `assemble_amenity_records` | `(state: AmenitySearchState) -> AmenityRecordSet [raises: ResultAssemblyError]` | pre-indexed merge: build indexes, join per (category, place), wrap envelope |
| `project_place_profile` | `(place: dict) -> dict` | M1.3.a: null-on-missing projection of profile fields, snake_case keys |
| `convert_route_leg` | `(leg: RouteLeg \| None) -> RouteView \| None` | M1.3.b: meters/seconds to km/min at 2 decimals, or null |
| `convert_transit_leg` | `(leg: TransitLeg \| None) -> TransitView \| None` | M1.3.b: km/min plus used_fallback, or null |
| `convert_accessibility` | `(bundle: EnrichmentBundle \| None) -> tuple[dict[str, RouteView \| None], TransitView \| None]` | M1.3.b: per-mode routing map and transit view for one place |

**`create_amenity_search`** (existing): unchanged. M1.3 adds no injected dependency.

## E. Runtime Flow: Data Object Journey

One request is one `AmenitySearchState` carrying `discovered_places`, `enrichment`, and
`category_metric_plans`. The sample runner and the fixtures are excluded.

| # | Stage method | Reads | Produces / mutates | Object shape after |
| --- | --- | --- | --- | --- |
| 1 | `run_result_attachment` | state | calls assemble, assigns envelope, logs | `state.amenity_records` set |
| 2 | `assemble_amenity_records` | `discovered_places`, `enrichment`, `category_metric_plans` | builds `plan_index` + `accessibility_index`; per (cat, place) record | `AmenityRecordSet` |
| 3 | `convert_accessibility` (per bundle) | one `EnrichmentBundle` | `(routing_map, transit_view)` | one `accessibility_index` entry |
| 4 | `project_place_profile` (per place) | `CanonicalPlace.place` dict | profile field dict | profile values, null on missing |
| 5 | (construct) `AmenityRecord` | profile + accessibility + plan | frozen record | record at `records[cat][place]` |

**Transformation trace (shape only):**
```
AmenitySearchState{ discovered_places{cat->place->CanonicalPlace}, enrichment{place->EnrichmentBundle},
                    category_metric_plans[], amenity_records: None }
 -> accessibility_index{ place_id -> ( routing_map{mode->RouteView|None}, transit: TransitView|None ) }
 -> plan_index{ category_id -> CategoryMetricPlan }
 -> per (category_id, place_id): AmenityRecord{ identity, depth, profile fields (X|None), routing, transit }
 -> AmenityRecordSet{ contract_version, records{ category_id -> { place_id -> AmenityRecord } } }
 -> AmenitySearchState.amenity_records = AmenityRecordSet
```

**Approach at the real decision points:**
- Pre-indexed merge (Stage c): build `accessibility_index` by converting each `enrichment` bundle
  once (keyed by place_id); build `plan_index` from `category_metric_plans` by category_id; then
  iterate `discovered_places` (category_id, then place_id).
- Join per pair: project the `CanonicalPlace.place` profile; look up
  `accessibility_index.get(place_id)`, defaulting to an all-`None` routing map plus `None` transit
  when the place is absent from `enrichment` (record still built, not skipped); read
  `plan_index[category_id]` for `depth` and `taxonomy_node`, raising `ResultAssemblyError` when a
  discovered category has no plan.
- Projection null-on-missing (Stage a): read each field by its snake_case key with chained `.get`;
  `name` is `display_name.text`; `coordinates` is `GeoPoint(location.latitude, location.longitude)`
  or `None` when `location` is missing; opaque objects (`opening_hours`, `reviews`) are copied as
  returned; any missing key yields `None`.
- Unit conversion (Stage b): `distance_km = distance_m / _METERS_PER_KM` rounded to 2 decimals;
  `duration_min = duration_s / 60` rounded to 2 decimals; a `None` leg maps to `None`; every
  `ROUTING_MODES` key is present in the routing map; `used_fallback` is copied from the `TransitLeg`.
- Envelope version (Stage c): `contract_version` is stamped once on the `AmenityRecordSet` from
  `AMENITY_RECORD_CONTRACT_VERSION`; no per-record version.

A reader who stops here knows: M1.3 reads the frozen places and their enrichment, converts units,
joins one record per (category, place) with nulls where data was absent, and hands a single
versioned `AmenityRecordSet` to M2.

## F. Method Detail

**`project_place_profile`**
- **Purpose:** turn one raw place dict into the record's profile fields with null on missing.
- **What it does:** read each field by its proto snake_case key; extract `name` from
  `display_name.text`; build `coordinates` as a `GeoPoint` from `location` or `None`; copy
  `opening_hours` and `reviews` as returned; assign `None` to any absent key; no unit conversion.
- **Inputs:** `place: dict`. **Outputs:** `dict` keyed by `AmenityRecord` profile field names.
  **Failure:** none (absence is null, never an error).

**`convert_route_leg` / `convert_transit_leg`**
- **Purpose:** convert one raw leg to a km/min view, or null.
- **What it does:** for a present leg, divide meters by `_METERS_PER_KM` and seconds by 60, round
  both to 2 decimals, build the frozen view (`TransitView` also copies `used_fallback`); for `None`
  return `None`.
- **Inputs:** `RouteLeg | None` or `TransitLeg | None`. **Outputs:** `RouteView | None` /
  `TransitView | None`. **Failure:** none.

**`assemble_amenity_records`**
- **Purpose:** join projected profile, converted accessibility, and plan fields into the versioned
  envelope.
- **What it does:** build the accessibility index (via `convert_accessibility` per bundle) and the
  plan index; iterate `discovered_places`; per (category_id, place_id) construct the frozen
  `AmenityRecord`; wrap the nested records in an `AmenityRecordSet` stamped with the contract
  version.
- **Inputs:** `state`. **Outputs:** `AmenityRecordSet`. **Failure:** `ResultAssemblyError` (stage
  `assemble_amenity_records`) when a discovered category_id has no matching plan.

---

## 4. Sample Runner and Fixture Set

Two checks, neither in the section E request path.

### 4.1 Live sample runner (required)

`feature_sample_runs/result_attachment_sample_run.py`. Manual, stage-by-stage over seeded state.
M1.3 makes no external call, so the runner makes none; it exercises the transform on dummy input.

- **How to run** from `backend/`:
  `python -m src.services.deep_search.feature_sample_runs.result_attachment_sample_run`
- **What it seeds** an `AmenitySearchState` as after M1.2: a hand-built `discovered_places` +
  `enrichment` + `category_metric_plans`. M1.1 and M1.2 are not re-invoked. The seed covers each
  branch: a place with a full profile and full routing/transit; a place missing optional fields
  (null projection); a `basic_profile` category (operating fields not requested); a place present
  in `discovered_places` but absent from `enrichment` (all-null accessibility); a routing mode set
  to `None`; transit set to `None`.
- **What it prints** one titled section per stage: input state; per-place projected profile; the
  accessibility index (converted views); the joined `AmenityRecordSet` with per-category counts;
  the written `state.amenity_records`. The completion event is read from `homescout.places` via a
  collecting handler. On a typed failure: exception class, `stage`, message, and a non-zero exit.
  Nothing written to disk.

### 4.2 Fixture set

`tests/services/deep_search/test_result_attachment.py`. Pytest over constructed state (no client,
no live call) asserting the code-path rules the runner cannot prove deterministically:
- projection extracts `name` from `display_name.text` and `coordinates` from `location`, keys on
  snake_case, and assigns `None` to every missing field;
- conversion divides meters by `_METERS_PER_KM` and seconds by 60, rounds to 2 decimals, returns
  float, maps a `None` leg to `None`, copies `used_fallback`, and keeps every `ROUTING_MODES` key;
- assembly keys records by (category_id, place_id) as a nested dict, and a place in
  `discovered_places` but absent from `enrichment` yields an all-null routing map and null transit
  rather than a skipped record;
- `depth` and `taxonomy_node` come from the matching plan; the envelope carries one
  `contract_version` and `AmenityRecord` has no `contract_version` field;
- a discovered category_id with no plan raises `ResultAssemblyError` with
  `stage == "assemble_amenity_records"`;
- `state.enrichment` is unchanged after the write.

---

# Architecture and Modularity Decisions

## Layer 1: Glance

### A. Architecture at a Glance
- **Shape:** three synchronous stage methods plus a thin workflow entry added to the existing
  `AmenitySearch` responsibility class, implementing a pure in-memory transform over the state
  M1.1 and M1.2 wrote. No new class, no client, no LLM, no prompt.
- **Seams (where things can change independently):**
  - Output contract shape (`AmenityRecord` / `AmenityRecordSet`) is the boundary M2 reads; version
    lives on the envelope.
  - Profile projection reads the raw place dict keys, so a discovery field-mask change flows
    through without a projection edit for existing fields.
  - Unit conversion is isolated in two converters, so the km/min/rounding policy changes in one
    place.
- **Component list:**
  - `AmenitySearch` M1.3 methods: the workflow entry and the three stages.
  - `AmenityRecord`: one amenity per category, all profile fields nullable.
  - `RouteView` / `TransitView`: converted leaf views for routing and transit.
  - `AmenityRecordSet`: the versioned envelope carrying the nested records.
  - `ResultAttachmentError` tree: the typed failure surface for the join.

## Layer 2: Justification

### B. Component Map

| Component | Owns | Depends on | Abstracted? |
| --- | --- | --- | --- |
| `AmenitySearch` M1.3 methods | projection, conversion, join, envelope write | existing state contracts | — (concrete) |
| `AmenityRecord` | one amenity per category, nullable profile | `RouteView`, `TransitView`, `GeoPoint` | — (frozen dataclass) |
| `RouteView` / `TransitView` | one converted leg value | — | — (frozen dataclass) |
| `AmenityRecordSet` | envelope: one version + nested records | `AmenityRecord` | — (frozen dataclass) |
| `ResultAttachmentError` tree | join-invalid exit with `stage` | — | — (exception tree) |

### C. Decisions and Justifications

| Decision | Current requirement that forced it | What breaks today without it |
| --- | --- | --- |
| M1.3 as methods on existing `AmenitySearch` | M1.3 reads the state M1.1/M1.2 wrote on that class | a new class duplicates the state handle and the ownership |
| `AmenityRecordSet` envelope, one `contract_version` | version stamped once, `amenity_records` is an envelope (locked) | a per-record version repeats one value on every record |
| `AmenityRecord` frozen, no `contract_version` | version is envelope-level (locked) | a per-record field contradicts the locked envelope decision |
| `RouteView` / `TransitView` typed views | downstream reads `distance_km`/`duration_min`/`used_fallback` | a bare dict lets a reader read a field with no shape guarantee |
| `ResultAssemblyError` with `stage` | assemble reads `plan_index` by category_id | a bare `KeyError` leaks instead of a typed, stage-named exit |
| All profile fields Optional | locked derive-on-read rule: no value is null | a non-null type lies when the API omits a field |

### D. Kept Concrete / Rejected

| Considered | Decision | Reason |
| --- | --- | --- |
| New M1.3 class / workflow class | rejected | M1.3 reads the existing `AmenitySearch` state; a class adds no boundary |
| Prompt module / LLM call | not added | M1.3 is deterministic; no natural-language step (locked D4.3) |
| Async methods for M1.3 | rejected | no I/O and only trivial in-memory CPU; nothing to await, gather, or offload |
| Thread / process offload | rejected | the work does not wait in a system call and holds no long CPU section |
| Per-record `contract_version` | rejected | version stamped once at the envelope (locked) |
| `_absent` set per record | rejected | absence is derived on read from `depth` (locked); no stored reason |
| A `ProfileProjection` dataclass | rejected | the projection output feeds one constructor; an internal dict suffices |
| Errors for projection / conversion | not added | both null-fill rather than fail; only the join has a real failure exit |
| Persisting `amenity_records` | not added | handoff is in-process and in-memory, as M1.1/M1.2 |

## Layer 3: Wiring

### E. Dependency Direction
```
AmenitySearch (M1.3) -> AmenitySearchState, discovered_places, enrichment, category_metric_plans (read)
AmenitySearch (M1.3) -> AmenityRecord, RouteView, TransitView, AmenityRecordSet (produced)
AmenitySearch (M1.3) -> ResultAttachmentError (typed exit)
```
No new external dependency: no client, no provider.

### F. Composition Root
- **Where:** `create_amenity_search(settings)` in `amenity_search.py`, unchanged. M1.3 injects
  nothing new.
- **Selects:** the version value `AMENITY_RECORD_CONTRACT_VERSION` as a module constant, beside
  `DISCOVERY_MAX_RESULTS` / `DEFAULT_RADIUS_KM`.

### G. Async Execution Map (per the async skill)
- **`run_result_attachment` / `assemble_amenity_records` / `project_place_profile` / `convert_*`.**
  Operations: dict reads, arithmetic (km/min), dataclass construction. I/O touchpoints: none. Data
  dependency: assemble needs both indexes before iterating; each record needs its projected profile
  and its converted accessibility. Placement: on the caller's thread, inline (the work does not
  wait in a system call and does not hold the interpreter lock, the lock that lets only one thread
  run Python code, for a long CPU section). Ordering: sequential; there is no independent I/O to
  overlap and no CPU section large enough to offload to a worker (a separate thread or process).
  Blocking check: trivial CPU that finishes quickly for the small per-request place set. Worker
  handling: none.

### H. End-to-End Flow
1. The caller (later the Feature orchestrator) invokes `run_result_attachment(state)` after M1.2
   has written `enrichment`.
2. `assemble_amenity_records` builds the accessibility index (converting each bundle to km/min
   views) and the plan index by category_id.
3. It iterates `discovered_places`; per (category_id, place_id) it projects the profile, joins the
   converted accessibility by place_id (all-null when the place is absent from `enrichment`), reads
   `depth` and `taxonomy_node` from the plan, and constructs a frozen `AmenityRecord`.
4. The records are wrapped in an `AmenityRecordSet` stamped with the contract version and assigned
   to `state.amenity_records`; `enrichment` is retained.

## Layer 4: Backing
- **Methods on `AmenitySearch`, not a new class:** M1.3 reads `discovered_places`, `enrichment`,
  and `category_metric_plans` already owned by `AmenitySearch`, so a stage lives as a method beside
  `run_place_discovery` and `run_accessibility_enrichment`.
- **Envelope version, not per record:** the version identifies the shape of the whole
  `amenity_records` object handed downstream, so it is stamped once on the envelope and not
  repeated on every record.
- **Synchronous:** the transform reads in-memory dicts and does arithmetic and dataclass
  construction; there is no socket, disk, or database wait to overlap and no long CPU section to
  run in parallel, so the methods run inline and are not marked async.
- **Typed views for routing / transit:** downstream reads `distance_km` and `duration_min` per mode
  and a `used_fallback` flag; frozen `RouteView` / `TransitView` give those a fixed shape and keep
  `None` distinct from a zero-valued leg.
- **Optional profile fields:** the locked derive-on-read rule stores null for any field the API did
  not return and derives the reason from `depth`, so every projected field is nullable and no
  default is fabricated.
- **Defensive join error:** the join reads the plan by category_id; a category present in
  `discovered_places` without a plan is a malformed state, so it exits as a typed
  `ResultAssemblyError` naming the stage rather than a bare `KeyError`.

---

## Cross-mechanism note

`AmenitySearchState` gains `amenity_records: AmenityRecordSet | None`. Additive; M1.1 and M1.2 code
and tests do not read it, so nothing breaks. The `deep_search_context.md` M1.3 section is updated
to carry the envelope-level version, the nullable profile fields, and the M1.3.a/b/c sub-components.
