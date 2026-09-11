Google Places API Integration with Deep Search feature

Hierarchy in deep search feature:

Listings & their Quality
2. Apartment Amenities
3. Neighborhood Quality
Essentially Deep search is just going to be an orchestrator. And we can consider its responsibilities as feature itself and they will be orchestrated by Deep Search.





Problem Context of the feature (Neighborhood Quality):
Overall Feature Problem:
The feature needs to determine whether the neighborhood surrounding an apartment meets the user's stated preferences by identifying relevant amenities and providing reliable information about their proximity, accessibility, characteristics, and quality. The information must be sufficiently specific to the user's requirements at the required level of depth rather than presenting a generic list of nearby amenities, while distinguishing factual information and information in the form of metrics about each amenity from assessments derived from that information.


User:
Stakeholder 1: Customer
Want (Preference Match): knowing which of the amenities he actually cares about exist nearby. Friction: manually checking a map means searching for each preferred amenity type one at a time and cross-referencing distance himself, with no single view of whether his actual list of priorities is met.

Want (Scoped Search): controlling how far out from the listing counts as "the neighborhood" for his purposes. Friction: without this, he's stuck with whatever fixed radius a generic search happens to use, which may be too tight or too wide for what he considers relevant.

Want (Real Accessibility, not just distance): *[added]* knowing whether an amenity is actually easy to get to, not just physically close as a straight line. Friction: a raw distance number hides whether the route is walkable, crosses a highway, or takes far longer in practice than the distance implies, and he has no way to know this without visiting himself.

Want (Structured Presentation): seeing amenity information organized by type and metric, not as a raw, unsorted list. Friction: scrolling through unfiltered map results mixes relevant and irrelevant entries together, forcing him to mentally sort and discard as he reads.

Want (Right-Depth Detail): getting the right amount of information per amenity type, more where he cares more, less where he doesn't. Friction: manually researching every amenity to the same depth wastes his time on things he's indifferent to, while a single shallow pass misses what he actually wanted detail on.

Want (Characteristic Match): amenities matching a specific quality he asked for, or a reasonably close alternative to it, rather than just anything of the right category. Friction: a generic search returns everything labeled "gym" or "park" regardless of whether it has the specific quality he wanted, forcing him to individually check each one to confirm it fits.

Want (Baseline Coverage): still getting some information about amenity types he didn't think to mention. Friction: if he forgets or doesn't know to ask about a category, he's left completely blind to it, even though it may affect his decision.

Want (Self-Sufficient Evaluation): evaluative information being available even for things he didn't know to ask for. Friction: without this, he only gets an assessment for the exact 
metrics he specified, and has no way to judge anything outside the boundaries of his own request.

Want (Non-Redundant Selection): *[added]* not being handed every single instance of a common amenity type when a few representative ones would tell him what he needs. Friction: a raw list of all 15 nearby cafes buries the ones actually worth knowing about, and he has to manually skim all of them to find what matters.

Want (Judgment Traceability): *[added]* being able to see why an amenity was judged as fitting or not, not just told a verdict. Friction: a bare score or pass/fail with no reasoning behind it can't be checked against his own judgment, so he either has to blindly trust it or re-verify it himself.

Want (Direct Relevance): reading a result that speaks to his specific requirement, not a generic summary he has to reinterpret against his own priorities. Friction: a generic report requires him to manually map broad information back onto his own specific ask, redoing the comparison himself.

Stakeholder 2: Developer
Want (Minimal Reprocessing): relying on data that's already structured and evaluative, rather than raw data he has to clean and interpret himself. Friction: without this, every amenity source requires building custom extraction and normalization logic before it's even usable.

Want (Depth on Demand): being able to go from a basic fact about an amenity to a deeper one when the situation calls for it, without switching to a completely different approach. Friction: without this, going deeper than a surface-level lookup means improvising a separate method each time, per amenity, per situation.

Want (Guaranteed Baseline Metrics): a fixed, reliable set of metrics that gets pulled for every amenity type regardless of whether the user asked, so nothing obviously relevant is left out by default. Friction: without this, what counts as "obviously relevant" is left to be reasoned out fresh every time, risking inconsistent or missing baseline information across amenity types.

Want (Tool Usage): Get useful information about an amenity using the preferred tools(Google Maps API, LLMs, Diffbot extractor, Parallel Web Search) and can add more tools if additional information can be fetched by using them.

Want (Fact/Assessment Separation as a structural rule): *[added]* an explicit, enforced boundary in the output between what was directly retrieved and what was concluded from it. Friction: without a structural rule for this, facts and judgments can blend together in the output over time as more evaluation logic gets added, making it unclear later which parts are verifiable and which are interpreted.

**Completeness check:** if the customer gets preference-matched, genuinely accessible, appropriately-detailed, characteristic-matched, non-redundant amenity information with baseline coverage and traceable judgments, and the developer can rely on structured data, adjustable depth, guaranteed baseline metrics, tools, and a clean fact/assessment boundary, both sides would now consider this solved, including the two overall-problem terms (accessibility, fact-vs-assessment separation) that the original list didn't explicitly cover.


Environment:
Facts constraining what success can look like:
Users vary in how much they specify, some will name specific amenities and characteristics, others will name only a few or none, so the feature can't assume complete input every time.
What counts as a good or relevant characteristic for an amenity type differs by category (a gym's relevant quality isn't a park's), so "quality" isn't a single generic measure across all types.
Not every amenity type will have a perfect match to what the user asked for, so an alternative that's reasonably close has to count as a usable outcome, not nothing at all.

Facts constraining how the solution must operate:
The feature responsibility already has access to a specific set of tools (Google Maps, LLMs, Diffbot extractor, Parallel websearch), each suited to different kinds of information (structured location data vs. deeper page content vs. broader web facts), so no single tool covers every amenity's information needs by itself.
Some of these tools return pre-built, structured metrics directly, while others return raw content that has to be extracted and interpreted before it's usable, so the effort required differs by source, not just by amenity type.
Amenity information exists at more than one depth (a location and category, versus operating details, versus specific attributes), and not every user need requires the deepest level, so depth has to be adjustable per case rather than fixed.
The evaluative judgment about an amenity (whether it's "good," matches a characteristic, etc.) is a separate step built on top of the factual data, not something the raw data source provides on its own.

Completeness check: each fact explains why a naive, fixed-tool, fixed-depth, fixed-metric version would fail, differing input specificity would leave gaps for under-specifying users, a single tool would miss information types other tools are better suited for, and a fixed depth would either waste effort or under-serve deeper requests.

Problem relevance:
If amenity information isn't matched to what the user actually cares about, at the depth and characteristic level he cares about, and isn't clearly separated from the judgment drawn on top of it, he's left to manually re-derive relevance and quality himself from a generic report, which defeats the purpose of the feature responsibility doing that evaluation for him, and undermines his ability to trust the assessment when deciding whether a listing's surroundings actually fit his needs.


Actual Problem Statement:
The feature must first identify amenities within a user-defined radius of the listing, covering the amenity categories the user explicitly specified at full priority and a smaller, fixed set of common categories he did not specify, based on the understanding of his explicit and hidden requirements. For each identified amenity (in each category), it must retrieve a fixed baseline set of metrics using whichever available tool is best suited to that data (Google Places New API) and extending to deeper, page-level detail only where the user's stated need calls for it using additional tools like LLMs, Diffbot extractor and Parallel Web Search. For every amenity, it must compute travel-based accessibility (route, mode, time), not straight-line distance alone. Within each category, it must narrow results to a representative set, keeping only amenities that match a user-specified characteristic or a reasonably close alternative where such criteria were given, rather than returning every instance found. From this factual data, it must produce an assessment for every amenity (of every category), specified or baseline, keeping that assessment structurally separate from the underlying facts while carrying the specific facts it was derived from. Finally, the output must be organized by amenity category and metric, with depth scaled to how much the user specified about that category, and each result phrased against the user's stated requirement rather than as a generic summary.


Workflow of the Feature:
Shortlist the categories of amenities that we need to look for as per user preference
After shortlisting categories from explicit user preference, add a step that appends the fixed, predefined set of baseline amenity categories the user did not mention, before moving to metric definition. (This set of categories will be decided based on the user persona and analysis of he specified instructions)
Define the Baseline metrics, User specific metrics, User specific factual information at right level of depth, context of the user requirements that needs to bring for the user (one by one for all categories of amenities)
Search for amenities using Google Map APIs (one by one for all categories of amenities)
Shortlist the amenities from Google Map APIs results based on their relevance to respective category and fetch their relevant datapoints for the user (one by one for all categories of amenities)
Transform the datapoints into required format that will be used to share with the user
MUST TO HAVE: amenity candidates are shortlisted per category, that computes route-based accessibility (mode, route, travel time) for each amenity — distinct from and in addition to the raw geographic distance Google Maps returns.
MUST TO HAVE: Website, Name, Address
"We need to decide what would be rest of the datapoints"
Search for the information about every amenity that would allow to come up with user specific metrics and factual information at required depth (one by one for all categories of amenities)
Narrow to representative set based on user-specified characteristics after the deeper, user-specific factual search
Structure the additional information in a way that it can be merged into already extracted information
Now, based on the complete information which includes baseline metrics, user specific metrics, factual information at right depth, we need to generate the traceable judgement for each category of amenity.


Responsibilities of the feature:

1. User's Requirement interpretation (Responsibility-1 of the feature)

**Responsibility:** Determine what the user actually wants to evaluate.

Here are some of the sample points that can be addressed in this responsibility of the feature and we can add more as well:

Which amenity categories the user specified.
What categories user has not explicitly specified but might still find interesting based on their persona and requirements?
What characteristics matter for each category.
How much detail is needed.
What metrics are relevant to that particular requirement. And decide metrics for each category.
Which baseline metrics about different amenity categories should always be part of the results?

**Boundary:**
This responsibility should end with something like:

> "For restaurants, the user cares about X and Y, and these are the metrics/facts we need."

It should **not search for restaurants or retrieve their data**.


Problem Context of User's requirements interpretation:

User
Stakeholder: Customer

Want (Reasoning Capture): the feature responsibility understanding why an amenity category matters to him, not just that he mentioned it. Friction: a plain keyword match (he said "gym") captures the category but drops the reason behind it (proximity for daily use vs. a specific class type), so anything built on top of the bare keyword loses that context and can't use it later.

Want (Persona-Informed Inference): the feature responsibility inferring what he'd likely care about from how he's described his situation and priorities, not only from what he's explicitly typed. Friction: manually listing every category and characteristic he cares about is tedious and easy to under-specify, and he often doesn't think to mention something until he's confronted with its absence.

Want (Extended Relevance): the feature responsibility surfacing amenity categories he didn't mention but would plausibly care about, based on his stated lifestyle or situation. Friction: without this, anything outside his explicit list is invisible to the feature responsibility, even when it's a predictable extension of what he already said mattered.

Want (Explicit Priority): what he explicitly said always outweighing anything the feature responsibility infers on its own. Friction: without an enforced ranking, an inferred or default category could compete with or dilute attention that should go entirely to what he actually asked for.

Want (Right-Sized Depth): the feature responsibility deciding, per category, how much information is actually worth surfacing so he isn't left doing further digging himself. Friction: a fixed shallow or fixed deep pass either omits what he needed or drowns him in information he didn't ask for, and either way he ends up compensating manually.

Want (Fitness Sufficiency): the specification defined at each category being enough to actually tell whether an amenity serves his purpose, not just enough to describe it. Friction: if the specified metrics only describe an amenity generically (name, category, distance) without touching what makes it fit or not fit his purpose, he can't actually decide from it and has to investigate further himself.

Want (Ambiguity Resolution): the feature responsibility deciding a reasonable single interpretation when his stated requirement is vague or could mean more than one thing (e.g., "good gym" could mean equipment variety, class schedule, or crowd level), rather than picking one arbitrarily or trying to cover all meanings at once. Friction: today, vague requirements just get restated back at him unresolved, or he has to manually clarify what he meant himself.

Want (Category Boundary Correctness): a category he names being mapped to the correct real-world scope, not a broader or narrower one than he intended (e.g., "grocery" not silently including convenience stores if he meant a full grocery store). Friction: without this, mismatched scope produces a specification that looks complete but is quietly evaluating the wrong thing.

Want (Consistency Across Categories): the depth and metric decisions applied to one category not being arbitrarily different in rigor from another category he cares about equally. Friction: without an internal consistency check, one category could get a thorough specification and another a thin one, for no reason traceable to his actual stated priorities.

Completeness check: if every category (named or inferred) comes with a captured reason, an explicit-over-inferred priority, an appropriately scaled depth, and a set of metrics sufficient to judge match of categories, not just describe existence, the customer would consider this responsibility's job done, independent of how well the later search or evaluation steps execute.

Environment:
Facts constraining what success can look like: 
Customers vary in how much they state up front, from detailed characteristic-level information to a bare category name to nothing at all for a given category, so this responsibility can't assume a fixed amount of stated input to work from. There's no ground truth for "the correct" inferred category or characteristic, only a plausible-given-persona judgment, so inference here is necessarily probabilistic & can also be in the form asking user a bit more questions about few things to understand the specifications in better way, not something that can be verified as strictly right or wrong before the fact. What counts as a relevant characteristic or metric differs by category (what matters for a gym is not what matters for a park), so no single fixed template of characteristics or metrics applies uniformly across categories.
Facts constraining how the solution must operate: This responsibility runs before any search or retrieval happens, and its output (the specification) is the only input the later retrieval and evaluation stages receive, so an error or omission here propagates forward with nothing downstream positioned to catch or correct it. The customer's stated requirements arrive as unstructured, natural language, not as a pre-categorized list, so turning it into discrete categories, characteristics, and depth levels is itself part of the work, not a given. Explicit and inferred categories have to coexist in the same output, so the specification format has to be able to represent both without collapsing the priority distinction between them.
Completeness check: each fact explains why a naive version, one that only echoes back explicitly named categories at a fixed generic depth, would fail: it would miss anything unstated, apply the wrong characteristics to the wrong category types, and produce a specification too thin for the evaluation stage to judge fitness from later.

Problem relevance:
If this responsibility misreads what the customer actually needs to evaluate, or at what depth, everything downstream (search, retrieval, and the final judgment) ends up built on the wrong target: search retrieves the wrong things well, or the right things insufficiently, and no later stage is positioned to notice the original interpretation was off. This directly determines whether the customer's final decision about a listing's neighborhood is grounded in what he actually cares about, or in a generic guess dressed up as personalization.
Filter test: any capability written into this responsibility's problem statement should trace back to producing an accurate, appropriately prioritized, sufficiently deep specification per category. If a capability doesn't trace back to that, it belongs to a different responsibility (search, retrieval, or evaluation), not this one.


Actual Problem statement:
This responsibility must first parse the customer's stated requirements and instructions to come up with the discrete amenity categories, resolving each to its correct real-world scope and, where a stated characteristic for any category of amenity is vague or open to more than one meaning, resolving it to a single reasonable interpretation, and capturing the underlying reason behind why each explicit category matters to him. These explicit categories and their captured reasoning are treated as fixed, top priority input in the context of customer's described persona, situation, and lifestyle,. Next, based on the customer's described persona, situation, and lifestyle, it must infer additional categories and their characteristics he did not explicitly state, appended below the explicit set as lower-priority, probabilistic additions that cannot compete with or dilute what was explicitly stated. For every category, explicit or inferred, it must assign a depth of information (metrics, factual information, characteristics) to the surface, based on how much the customer specifications about that particular category or if not specified then understanding what level of depth a category amenity would require to evaluate it, applying this depth-assignment logic the same way across all categories rather than case by case. Finally, for every category, it must define the specific metrics and factual points, category-appropriate rather than drawn from one fixed template, that are sufficient to judge whether an amenity actually serves the customer's underlying purpose for wanting that category, not merely to describe that the amenity exists. The output of this responsibility is this specification per category (reason, priority, depth, metrics) and nothing beyond it, no search or retrieval of amenities happens here.

Filter check (problem relevance): every clause traces back to producing an accurate, appropriately prioritized, sufficiently deep specification per category, since anything wrong or missing here propagates uncorrected into search, retrieval, and the final judgment. Nothing here performs search or retrieval, which belongs to a later responsibility.



Implementation Mechanisms of the User's Requirement Interpretation:

Process Flow — "User's Requirement Interpretation" Responsibility

Scope reminder: everything below stops at producing a per-category specification (reason, priority, depth, metrics). Nothing here searches, retrieves, or scores an actual amenity — that starts in the next responsibility, which consumes this one's output as its only input.

Mechanisms identified
Unstructured Input Parsing (prerequisite)
2. Explicit Category Resolution
3. Router --> Global Requirement Sufficiency Gate --> Explicit Category Resolution
4. Explicit Reason Capture & Priority Tagging
5. Router --> Explicit Category Detail Elicitation --> Explicit Reason Capture & Priority Tagging
6. Persona-Driven Category Inference
7. Depth Assignment
8. Category-Specific Metric & Fact Definition
9. Specification Assembly & Priority Enforcement


Process Flow — "User's Requirement Interpretation" Responsibility

Scope reminder: everything below stops at producing a per-category specification (reason, priority, depth, metrics). Nothing here searches, retrieves, or scores an actual amenity — that starts in the next responsibility, which consumes this one's output as its only input.

Mechanisms identified
Unstructured Input Parsing (prerequisite)
2. Explicit Category Resolution 
3. Router --> Global Requirement Sufficiency Gate --> Explicit Category Resolution
4. Explicit Reason Capture & Priority Tagging
5. Router --> Explicit Category Detail Elicitation Resolution --> Explicit Reason Capture & Priority Tagging
6. Persona-Driven Category Inference
7. Depth Assignment
8. Category-Specific Metric & Fact Definition
9. Specification Assembly & Priority Enforcement

Dependency flow: 1 → 2.1 → 2.2 → 3.1 → {4.1 ∥ 5.1} → 5.2 → 6.1
(5.1 only needs the finalized category set from 3.1, so it can run alongside 4.1; 5.2 needs both the depth from 4.1 and the reason from 2.2, so it waits on both.)

Mechanism 1 — Unstructured Input Parsing
Component: Requirement & Persona Extraction

Goal of Component: Convert the customer's raw natural-language input into a structured intermediate representation that keeps three things separate: (a) explicit category (b) category characteristics, (c) phrases flagged as ambiguous, (d) general persona/situation/lifestyle facts.

Problem It Aims to Solve: Every later component needs to know whether it's looking at "something the customer asked for" or "background about who he is" — if these get conflated at extraction time, reasoning capture and inference downstream have no reliable signal to work from.

Approach:
Single-pass structured extraction: one LLM call with a fixed output schema that extracts categories, characteristics, ambiguity flags, and persona/lifestyle/situation facts together. At this stage, we are not mapping the categories to our amenity-categories list. We just want to extract the amenities which user has mentioned in their response. The extraction model does not emit identifiers.

Extraction-owned category identity (`category_id`):
When Mechanism 1 assembles `ExtractedRequirements`, each `explicit_categories` entry is labeled with a stable `category_id` in code, by list position. Flagging a phrase does not remove it from its bucket, so every `target: "category"` flag has exactly one backing explicit entry; that flag is stamped with the same `category_id` in the same assembly pass. A category flag that does not resolve to exactly one backing entry is a validation failure, not a defensive workaround. There is no separate `flag_id`. This id is the single key for the Mechanism 2 clarification loop (`user_responses`, 2B questions, 2A Operation 2). Names stay on the extracted entry; later models echo ids only.


-----------------------------------------------------------------------------------
-----------------------------------------------------------------------------------
Mechanism - 2 

# Component 2A: Category Scope & Ambiguity Resolution

## Goal of Component

Two operations, run in sequence:

1. **Taxonomy mapping (always runs):** Map every explicit category from the
   extraction to its correct node in the maintained amenity-category taxonomy,
   using the category name, its characteristics, and surrounding persona context
   to select the right node. The mapping model receives each category already
   labeled with `category_id` and echoes only that id plus a taxonomy node (or
   lists the id as unmapped). Assembly looks up `explicit_categories[category_id]`
   for `raw_name` and characteristics. Any category that cannot be confidently
   mapped becomes an unresolved-category ambiguity flag carrying that same
   `category_id`.

2. **Ambiguity resolution (conditional — runs only when user responses exist
   on the `RequirementInterpretationState`):**
   Take only the ambiguity flags whose target is **"category"** (those created
   from unmapped `category_id`s in operation 1, which already include categories
   Mechanism 1 had flagged) and resolve each one against
   `user_responses[category_id]` and surrounding context. A resolved "category"
   flag becomes a taxonomy-mapped entry in resolved explicit categories, with
   name and characteristics attached from `explicit_categories[category_id]`. If
   a flag's paired user response still does not provide enough evidence to
   resolve confidently, the component maps it to the nearest most-fitting node
   in the taxonomy rather than leaving it unresolved — once user responses
   exist, every category flag must exit this operation as a resolved taxonomy
   entry. Flags with target "characteristic" are **not processed** by this
   component — they pass through to ambiguity_flags as-is.

When `user_responses` on the `RequirementInterpretationState` is empty (first
pass, before any clarification round has occurred), operation 2 is skipped
entirely. The ambiguity flags from operation 1 are the final ambiguity flags.


## Problem It Aims to Solve

A raw category label from mechanism-1 can silently include or exclude adjacent
real-world entities: "grocery" and "convenience store" overlap but are not the
same scope. Without mapping to a defined taxonomy node, downstream components
cannot know what set of real-world places the customer meant, and two runs on
similar inputs can evaluate different scopes.

Separately, a category-level ambiguity flag ("a place to get my shopping done")
cannot be taxonomy-mapped until the customer clarifies what category they meant.
Without resolving it here, the category either never enters the resolved set or
downstream components guess the mapping — both produce results the customer did
not ask for. Characteristic flags are carried through unchanged for other
components to handle.


## Approach: Context-Aware Taxonomy Mapping

For each explicit category, provide the LLM with:
- the mechanism-1 output that this component received (categories already labeled
  with `category_id`),
- the full maintained amenity-category taxonomy.

The LLM selects the taxonomy node that best fits the customer's intended amenity
given all available context. It echoes the `category_id` it was handed; it does
not invent new taxonomy nodes, rename existing ones, echo category names, or
return a category outside the taxonomy.

For ambiguity resolution (when user responses are present), the same context-
aware approach applies but only to flags with target "category": each such
flag is evaluated together with `user_responses[category_id]` and surrounding
context to select a taxonomy node, and the model echoes that same `category_id`.
If the user response is still insufficient, the LLM maps the flag to the nearest
most-fitting taxonomy node rather than leaving it unresolved. Characteristic
flags are outside this component's resolution scope.


## Critical Decision Choices


### What counts as a valid resolution

A raw category is considered resolved if and only if it maps to exactly one
node in the maintained amenity-category taxonomy. Any mapping that would
require inventing a node, splitting across multiple nodes, or leaving the
taxonomy is not a valid resolution.

This component does not resolve characteristic flags. Their resolution is
outside 2A's scope.


### Output object: ResolvedRequirements

This component produces a new object — `ResolvedRequirements` — with four
fields:

| Field | Type | Content |
|---|---|---|
| `payload` | `PayloadRecord` | Carried from the mechanism-1 object unchanged. This component does not add, remove, or modify the payload. |
| `resolved_explicit_categories` | `list[ResolvedCategory]` | Every category that was successfully mapped to a taxonomy node. Each entry carries: `category_id` (the extraction-owned identity of the backing explicit category), `taxonomy_node` (the matched taxonomy identifier), `raw_name` (the original wording from mechanism-1), `characteristics: list[str]` (carried from mechanism-1 unchanged — this component does not modify characteristics), and `provenance` (one of `"confident"`, `"nearest_node"` — indicates whether the mapping was a confident match or a nearest-node fallback). |
| `ambiguity_flags` | `list[AmbiguityFlag]` | All flags this component did not resolve. Contents depend on the pass: **First pass (no user responses):** (a) all mechanism-1 flags whose target is not `"category"` (characteristic/persona, passed through untouched), plus (b) one `target: "category"` flag per unmapped `category_id` from Operation 1, carrying that id. Mechanism-1 category flags are not unioned on top of (b) — that would duplicate the same `category_id`. **Second pass (user responses present):** only mechanism-1 flags with target "characteristic" (and persona) remain — all category flags are resolved (confidently or to the nearest taxonomy node), so no category flags survive into this field. |
| `persona_facts` | `list[str]` | Carried from the mechanism-1 object unchanged. This component does not add, remove, or modify persona facts. |


### How raw categories that fail taxonomy mapping are handled

When an explicit category cannot be confidently mapped to a single taxonomy
node, it is **not** silently dropped. Assembly converts each id in
`unmapped_category_ids` into an ambiguity flag with `target: "category"`,
`category_id` set to that id, and `phrase` taken from
`explicit_categories[category_id].name`. This is the flag 2B keys its question
and the customer's answer on. No name string is echoed by the mapping model.


### How mechanism-1 ambiguity flags are carried

Mechanism-1 flags whose target is not `"category"` are copied into this
component's `ambiguity_flags` field unchanged. Category flags after Operation 1
come only from `unmapped_category_ids` (one flag per id). If Mechanism 1 had
already flagged a category and Operation 1 maps it confidently, that category
enters `resolved_explicit_categories` and no category flag remains for it. This
merged list is the starting set that operation 2 works on (if user responses
exist) or the final set (if user responses are empty).


### Conditional gate: user responses empty vs. present

**User responses empty (first pass):**
Operation 1 (taxonomy mapping) runs. Operation 2 (ambiguity resolution) is
skipped because the `user_responses` field on the `RequirementInterpretationState`
is empty. The ambiguity-flags field contains the merged set from mechanism-1
plus any failed-mapping flags, and nothing is resolved further.

**User responses present (after a clarification round):**
Both operations run. Component 2A reads `user_responses` from the
`RequirementInterpretationState`, keyed by `category_id`. Only flags with
target "category" are processed:

- **Flag target is "category":** Read `user_responses[category_id]` and the
  surrounding context. Attempt to map it to a taxonomy node. If the user
  response provides enough evidence, map it confidently. If the user
  response is still insufficient, map it to the **nearest most-fitting
  taxonomy node** — once user responses exist, every category flag must
  exit as a resolved taxonomy entry. In either case, attach `raw_name` and
  characteristics from `explicit_categories[category_id]`, add it to
  `resolved_explicit_categories`, and remove it from `ambiguity_flags`.

- **Flag target is "characteristic":** Not processed by this component.
  These flags remain in `ambiguity_flags` exactly as received.



Here are the revised **Router** and **Component 2B** specs, aligned to the final `category_id` pre-requisite (no `flag_id`, no echoed names, single loop key).

---

# Router: Category Resolution Check

## What it is
A conditional check that is one step inside **Mechanism 2** (alongside 2A and 2B), sequenced by a Mechanism-2 orchestrator. It is not a component: no LLM call, no transformation, no output object. After each 2A pass it reads the workflow state, owns the pass counter, and makes one binary branch decision.

## Input
The full `RequirementInterpretationState`. It reads `state.resolved.ambiguity_flags` to decide and forwards the **whole state** onward, so 2B can write to it and 2A's second pass can read it.

## Decision
Let `has_category_flag = any(f.target == "category" for f in state.resolved.ambiguity_flags)`.

| Condition | Branch |
|---|---|
| `has_category_flag` is True | Forward state to **Component 2B** |
| `has_category_flag` is False (only `characteristic` and/or `persona` flags, or none) | Forward state to **Mechanism 3** |

`characteristic` and `persona` flags never route to 2B; both fall through to Mechanism 3.

## Loop constraint (enforced structurally)
The router owns `state.category_resolution_passes`, incremented each time it inspects a fresh 2A output.

1. **Pass 1** (`user_responses` empty): category flags may exist → route to 2B.
2. **Pass 2** (`user_responses` populated by 2B): 2A Operation 2 guarantees zero surviving category flags — the customer cannot skip a question, so every category flag has a response keyed by its `category_id`, and each resolves confidently or via nearest-node. Router clears to Mechanism 3.

Hard cap: the router MUST NOT route to 2B when `category_resolution_passes >= 2`; it routes to Mechanism 3 unconditionally. This is a defensive guard; the guarantee should make it unreachable.

---

# Component 2B: Category Clarification Questions

## Goal of Component
Three ordered operations, each depending on the previous completing:

1. **Generate questions (LLM):** one clarification question (with options) per category flag, in a single batched call.
2. **Present and collect (CLI):** show each question and its options in the CLI and block until the customer provides a response. A response is mandatory.
3. **Write to state:** write each `{question, options, response}` into `state.user_responses`, keyed by the category flag's `category_id`.

## Problem It Aims to Solve
When 2A's first pass leaves category flags unresolved, those categories have no taxonomy mapping and cannot enter `resolved_explicit_categories`. 2B is solely responsible for generating grounded clarification questions, collecting the customer's answers, and handing them to 2A via the state under each flag's `category_id`. What 2A does with those answers afterward (confident mapping vs. nearest-node fallback) is 2A's concern, not 2B's.

## Approach: Instruction-Grounded, Batched Question Generation
A single LLM call receives all `target: "category"` flags (each carrying its `category_id`) plus grounding context from `state.resolved` (`resolved_explicit_categories`, `payload`, `persona_facts`, `ambiguity_flags`) and returns one question per flag. Constraints:

- Grounded strictly in the customer's own wording and existing context; introduces no assumptions about unstated needs.
- Purpose is only to clarify **what the stated category maps to in the amenity taxonomy** — not a preference, discovery, or new-requirement prompt.
- One question per category flag; no bundling, so answers map back by `category_id`.

### Output contract — question-generation call
LLM output `ClarificationResult`:

| Field | Type | Content |
|---|---|---|
| `questions` | `list[ClarificationQuestion]` | One entry per submitted category flag |

`ClarificationQuestion`:

| Field | Type | Content |
|---|---|---|
| `category_id` | `int` | Identity of the category flag this question is for (echoed from input) |
| `category` | `str` | The flagged category phrase, for display and grounding |
| `question` | `str` | The clarification question |
| `options` | `list[str]` | Candidate interpretations to show the customer |

Reuses `self._providers` and the `_call_providers` helper with a new `CLARIFICATION_SCHEMA_NAME`; total provider failure raises a typed `ClarificationProviderError`.

## Critical Decision Choices

### What 2B reads
`state.resolved` (`ResolvedRequirements`): `ambiguity_flags` filtered to `target: "category"` (which flags need questions, each carrying its `category_id`), plus `resolved_explicit_categories`, `payload`, and `persona_facts` for grounding. 2B receives the full state (the router passes it through) so it can also write `user_responses`.

### What 2B produces
No new object. It populates `state.user_responses`, keyed by `category_id`:

| Key | Value (`UserResponse`) |
|---|---|
| `category_id` (int, from the category flag) | `{ question: str, options: list[str], response: str }` |

`category_id` is unique per explicit category by construction (assigned at extraction), so keys never collide and no string matching is involved.

### Human-in-the-loop step (CLI)
After generation, 2B prints each question and its options to the CLI and reads the customer's typed answer. Synchronous and blocking; the workflow does not proceed until answered. A response is mandatory — a blank/empty answer is re-prompted, never accepted. This mandatory-response rule is what lets the Router guarantee hold.

### What happens after 2B completes
`state.user_responses` now has one entry per category flag, keyed by `category_id`. The Mechanism-2 orchestrator re-enters **2A for a second pass that reuses the existing `state.resolved`** (it does NOT rebuild it from scratch): Operation 1 taxonomy mapping is skipped, and Operation 2 runs over the surviving category flags, each paired with `user_responses[category_id]`. Every category flag exits resolved (name and characteristics attached from `explicit_categories[category_id]`); the router then clears to Mechanism 3.

### What 2B does NOT do
- Does not resolve ambiguity (2A's job).
- Does not generate questions for `characteristic` or `persona` flags.
- Does not modify `resolved_explicit_categories`, `ambiguity_flags`, or `persona_facts`. Its only write is `state.user_responses`.
- Does not run more than once per request.

---

# Part 3 — Before/After state and residual gaps

**Before 2B** (state after 2A pass 1, category flags present):
- `state.resolved.ambiguity_flags`: at least one with `target: "category"` (each carrying a `category_id`), plus any characteristic/persona flags
- `state.user_responses`: `{}`
- `state.category_resolution_passes`: 1

**After 2B** (before 2A pass 2):
- `state.resolved.*`: unchanged (2B writes nothing here)
- `state.user_responses`: one `{question, options, response}` per category flag, keyed by `category_id`
- `state.category_resolution_passes`: 1 (router increments on its next inspection)

| State field | Before 2B | After 2B |
|---|---|---|
| `resolved.resolved_explicit_categories` | Op1 confident mappings | unchanged |
| `resolved.ambiguity_flags` | category + characteristic/persona | unchanged |
| `resolved.persona_facts` / `payload` | carried | unchanged |
| `user_responses` | `{}` | one entry per category flag, keyed by `category_id` |
| `category_resolution_passes` | 1 | 1 |

---------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------



Mechanism - 3: Category Reasoning, Priority Tagging and Category reasoning exploration

Component 3A: Explicit Reason Capture & Priority Tagging
Goal of Component: For each scope-resolved explicit category, derive why the customer likely wants it (using persona/situation, not just the literal mention), and tag it as explicit, top-priority.
Problem It Aims to Solve: A bare keyword match ("he said gym") drops the motivation behind it, so nothing downstream can tell "gym for daily convenience" from "gym for a specific class type" — and without a captured reason, later metric selection has no purpose signal to key off.

Approach: Batch Contextual Reasoning with Evidence-First Reason Capture
Use a single LLM reasoning pass across all scope-resolved explicit categories, providing the full customer specification, persona/situation context, and all resolved categories. For each category, first derive the customer's reason from nearby/local wording when the reason is directly supported by the text. If no explicit reason is available, infer a reasonable persona/situation-based default for that category. Record the reason together with its source — explicit/local evidence or persona-based inference — so downstream systems can distinguish stated motivations from inferred ones. The LLM should reason across categories together to maintain consistency and avoid contradictory or redundant interpretations.

Critical Decision Choices:
Generic: how "priority = explicit" is represented in the data model so it can't be silently overwritten by a later step.
	Decision: explicit_high
Context-specific: Whether a captured reason can hold more than one motivation for a single category — relevant because depth and metric selection later both key off reason completeness, so an overly terse single-reason model risks under-specifying everything downstream of it.
	Decision: Yes, one category can hold multiple reasons.

NOTE: In the output component must provide the verdict if it is able to find out the reasoning associated with the categories. In case, it says "Lack of reasoning" for categories which did not have any contextual details then it triggers the Component 3B otherwise it moves on to the mechanism 4 using the ROUTER.


Component 3B: Explicit Category Detail Elicitation
Goal of Component: For each explicit category that has passed scope resolution, initial check by Explicit Reason Capture & Priority Tagging (3A) but carries no/vague attached characteristic or contextual detail, ask a targeted follow-up question to surface what the customer actually cares about within that category — before reason capture or metric definition treats it as finalized.

Problem It Aims to Solve: A category named with zero accompanying detail ("gym," nothing else) gives reason capture nothing to differentiate it from a generic default — this is exactly the "plain keyword match drops the reason" friction the problem context calls out. Left unaddressed, it produces a technically-present but practically-generic reason, which then produces generic purpose-fit metrics, silently degrading the one category the customer explicitly cared about most.

Batched propose-and-confirm clarification:
Collect all explicit categories that lack sufficient context, then generate a single consolidated clarification round covering them. For each category, use persona and situation context to propose the most likely relevant characteristic, requirement, or reason, and ask the customer to confirm, correct, or skip it rather than answering from scratch. Keep all proposed interpretations grounded in information already provided by the customer.
Here are scenarios & nature of questions that can be asked:

| Input                      | Action                          |
| -------------------------- | ------------------------------- |
| Categories but no context  | Ask category-specific questions |
| Ambiguity flags            | Ask only about gaps             |
| Sufficient information     | Proceed without clarification   |

Trigger clarification questions only when:
1) The customer specifies categories but provides no supporting context, reasoning, or situation that can meaningfully guide further resolution or inference.
	When triggered, it must not generate more than 5 targeted questions in total, based strictly on information already provided by the customer. Each question should seek to expand or clarify 	existing instructions rather than introduce assumed preferences.


NOTE: User response will be grounded in "category reasoning responses" and it will be passed to the Component 3A again so, that it can associate the reasoning to the categories using additional details provided by the user for some categories. Now, in case customer doesn't respond or declines to elaborate on a given category then we have to infer a basic generic reasoning for it which will trigger basic level of depth moving forward.


Mechanism 4 — Persona-Driven Category Inference
Component: Lifestyle-Based Category & Characteristic Inference

Goal of Component: From persona/situation/lifestyle facts, infer additional categories (MUST BE FROM DEFINED TAXONOMY) and characteristics the customer didn't state but would plausibly care about, without duplicating anything already in the explicit set, tagged as lower-priority.

Problem It Aims to Solve: Without this, anything outside the customer's explicit list is invisible to the specification, even when it's a predictable extension of what he already said mattered.

Approach:
Direct persona-to-category LLM inference: one call that takes persona facts plus the finalized explicit category list (for dedup) and proposes additional categories with characteristics and reasoning (that will explain what backs this inference).

Critical Decision Choices:
Generic: a cap or threshold on how many inferred categories are allowed, and how "plausibility" gets scored.
	Decision: Maximum 2
Context-specific: the dedup check must run against the resolved scope from Component 2.1, not raw customer wording — otherwise inference could re-add a category the customer already covered under different phrasing, which would violate explicit priority.
	Decision: Yes


Mechanism 5 — Depth Assignment
Component: Per-Category Depth Calibration

Goal of Component: Assign a depth level (how much information to surface) to every category — explicit and inferred — using one consistent decision logic applied uniformly.
Problem It Aims to Solve: A fixed shallow or fixed deep pass either omits what's needed or drowns the customer in unwanted detail; without one consistent logic, two equally-important categories could end up with arbitrarily different rigor.

Approach:
Category-norm depth lookup: derive a baseline expected depth per category type (researched — what level of detail a gym typically needs vs. a park), adjusted up/down only when stated detail deviates from that norm.

Critical Decision Choices:
Generic: the depth scale itself — how many discrete levels exist and what each concretely permits (e.g., basic profile details vs. operating details vs. specific attributes) — must be fixed before the logic can be applied consistently.
	Decision: Define a fixed depth scale with clear criteria for what information each level should capture respectively for every category depending upon the nature of the category. This provides a consistent basis for deciding how deeply each category should be analyzed and what is the baseline level for each category.
Context-specific: how inferred categories are capped relative to explicit ones — since they carry no stated detail by nature, a purely stated-specificity approach would default them all to minimum depth; a deliberate decision is needed on whether an inferred category can ever reach a deep level, given it must never compete with explicit attention.
	Decision: Always Lowest level of scale.


Mechanism 6 — Category-Specific Metric & Fact Definition

Component 6A: Baseline Metric Definition per Category, user-specific metrics

Goal of Component: For each category, define the fixed set of metrics/characteristics/facts that should always be captured for that category type, regardless of what the customer specifically asked.
Problem It Aims to Solve: Without a defined floor, "obviously relevant" information gets reasoned out fresh every time, risking inconsistent or missing baseline coverage — and the customer loses self-sufficient evaluation for anything he didn't think to ask about.

Approach:
Research-derived category baseline library: research, per category type, what facts are universally expected to judge that type, maintained as a standing reference reused every time that category appears. (Considering what we can extract using our tools like Google Places API, Diffbot, Parallel Web)

Critical Decision Choices:
Generic: whether baseline is purely category-type-specific, or has a small universal core (name, address, distance) layered under category-specific items.
	Decision: Some datapoints will be universal core (name, website, address, distance, travel time by different modes of transportation) and rest of the baseline metrics & factual information that we need to fetch would be category-type-specific and additionally driven by user instructions

Context-specific: How tightly this baseline should couple to the Google Places New API's actual return fields — this responsibility can't retrieve anything to verify that coupling itself, so over-anchoring risks defining a baseline the next responsibility can't actually fill, and under-anchoring risks an "ideal" baseline that's unretrievable.
	Decision: We have other tools that can be used to fetch additional and in depth and more specific information about amenities e.g. Diffbot (to extract and get information from website) and Parallel Web Search tool that allows to fetch information from web



Component 6B: Purpose-Fit Metric Definition per Category
Goal of Component: For each category, beyond baseline, define the specific metrics/characteristics/facts — category-appropriate, not templated — that let someone judge whether an amenity actually serves the captured reason for wanting that category, scaled to its assigned depth.

Problem It Aims to Solve: Metrics that only describe existence (name, category, website, distance & some more category-specific) don't let the customer decide fit — he'd still have to investigate himself, which defeats the responsibility's purpose.

Approach:
Reason-to-metric mapping: feed the captured reason and assigned depth, universally core (for dedup), baseline fixed set of metrics/characteristics/facts (for dedup), context of the user instructions to the LLM and have it output the relevant metrics that describes characteristics of the amenities at the right level of depth directly, category-appropriate rather than from a template.
 
Instructions:
Whichever approach is chosen, purpose-fit metric definition must run for every category in the finalized set — explicit and inferred alike, including ones with only baseline-level depth — so that even a shallow category carries at least a minimal relevant signal beyond bare existence facts.

Critical Decision Choices:
Context-specific: how to keep purpose-fit metrics distinguishable from baseline metrics within the same category record — this matters specifically because Mechanism 6 needs both feeding into one record without conflating "always-there" facts with "reason-specific" facts, which is also what the overall feature's fact/assessment separation rule downstream will build on.
	Decision: For every category we can keep them separate as baseline metrics & in-depth metrics in the same object.



Mechanism 7 — Specification Assembly & Priority Enforcement
Component: Unified Per-Category Specification Assembly

Goal of Component: Combine, for every category, its reason, priority tag, assigned depth level, and metric set (baseline + purpose-fit), factual info set, into one finalized record, structured so explicit categories remain dominant over inferred ones and rigor stays consistent across categories of equal priority.

Problem It Aims to Solve: Without an enforced assembly structure, an inferred category's fields could sit alongside explicit ones with nothing guaranteeing downstream consumers treat explicit as dominant — and no check would catch a category that ended up inconsistently under-specified relative to its peers.

Approach:
Two-block assembly: explicit and inferred categories assembled into two structurally separate blocks in the output, so priority is enforced by structure rather than by a field value that could be ignored downstream.

Important instructions: Regardless of assembly structure, every category's finalized record must include all four fields — reason, priority, depth, metrics, facts info — with none omitted. A category missing any one field produces a specification the next responsibility can't fully use, and nothing downstream is positioned to catch that gap.

Critical decision chioces:
Context-specific: whether cross-category consistency is checked automatically at assembly time or left as a design guarantee of Mechanisms 4 and 5's shared logic
	Decision: Through Structured Schema






			********-------------------------------------------------------------------------------------------------------------*************
*******-------------------------------------------------------------------------------------------------------------------------------------------------------------------*******
			********-------------------------------------------------------------------------------------------------------------*************




# Implementation of components of the User Requirements Interpretation Mechanisms: 

## Mechanism 1 -- Unstructured Input Parsing
Component-1: Requirement & Persona Extraction

Goal of Component: Convert the customer's raw natural-language input into a structured intermediate representation that keeps three things separate: (a) explicit category (b) category characteristics, (c) phrases flagged as ambiguous, (d) general persona/situation/lifestyle facts.

Problem It Aims to Solve: Every later component needs to know whether it's looking at "something the customer asked for" or "background about who he is" — if these get conflated at extraction time, reasoning capture and inference downstream have no reliable signal to work from.

Approach:
Single-pass structured extraction: one LLM call with a fixed output schema that extracts categories, characteristics, ambiguity flags, and persona/lifestyle/situation facts together. At this stage, we are not mapping the categories to our amenity-categories list. We just want to extract the amenities which user has mentioned in their response. The extraction model does not emit identifiers.

After validation, each explicit category is assigned `category_id` by list position, and every `target: "category"` flag is stamped with the `category_id` of its backing explicit entry. That identity is the single key Mechanism 2 uses; names are not re-derived later.




IMPLEMENTATION OF THE COMPONENT: REQUIREMENT & PERSONA EXTRACTION :-

Locked constraints carried into this breakdown
These are fixed at component level and are not reopened by any sub-component below.

* This component is the entry point of the responsibility. Its only input is the customer's raw natural-language input. Nothing upstream feeds it, and no state from any later component returns to it.
* Extraction happens in one model call with a fixed output schema (single-pass structured extraction). The model does not emit `category_id`.
* The call produces four separated buckets in one object: explicit categories, category characteristics, ambiguity flags, persona/situation/lifestyle facts.
* After the body validates, Mechanism 1 stamps `category_id` on each `explicit_categories` entry by list position, and stamps the same id onto every `target: "category"` flag from its backing entry (`phrase` must equal that entry's `name`). Zero or many matches is a validation failure.
* No taxonomy mapping happens here. Category strings are kept as the customer stated them. Mapping to the maintained amenity taxonomy is Component 2A, which echoes `category_id` rather than names.
* Counting resolved categories, applying the sufficiency threshold, and generating clarifying questions are not done here. Those depend on taxonomy-resolved categories, so they sit in Component 2A, the router, and Component 2B.
* No search, retrieval, depth assignment, or metric definition happens here.

### Sub-components

1. Input Intake and Payload Assembly
2. Intermediate Representation Schema
3. Extraction Instruction and Bucket Separation Rules
4. Constrained Call Execution and Response Validation
5. Parsed Output Assembly and Handoff Contract
6. Extraction Fixture Set and Bucket Placement Checks

Order: 1 → 2 → 3 → 4 → 5 → 6.

Sub-component 3 consumes the schema from 2. Sub-component 4 consumes the payload from 1 and the instruction plus schema from 2 and 3. Sub-component 5 wraps the validated object from 4 for Component 2A. Sub-component 6 runs the assembled path end to end.

---

### Sub-component 1: Input Intake and Payload Assembly ###

Goal of Component:
Turn the customer's raw natural-language input into one bounded, normalized payload that the extraction call receives.

Problem It Aims to Solve:
The customer's requirements arrive as unstructured text of unknown length, encoding, and formatting. The extraction call needs one fixed, bounded payload. Without an intake step, the call receives a string of arbitrary size and shape, and behavior changes with input length and formatting rather than with input content.

Finalized Approach:
3. Validate by checking encoding & length, Normalize and envelope. Produce a payload record holding the normalized text, a preserved copy of the raw text.
    Motive: “Validate and Clean the input, preserve the original as well.”

Critical Decision Choices:
* Minimum accepted input length should be 100 words and maximum length does not matter here and under-limit input is rejected with error "Instructions must be of more than 100 words"
* In case of empty or whitespace-only, input rejected at intake and will be shown error related to under-limit input.
* character offsets will not be preserved. 
* Yes, raw text will be stored alongside the normalized form.
* Yes, formatting markup (line breaks, bullets, quotes) is supposed to be preserved, since it can carry list structure the model reads as separate statements.
* Non-English input will be rejected.

---

### Sub-component 2: Intermediate Representation Schema ####

Goal of Component:
Define the machine-checkable output contract that holds the four buckets as separate fields, with a per-item field set for each.

Problem It Aims to Solve:
The four kinds of information must stay separated at extraction time. Without an enforced contract, the model response mixes a stated requirement with a background fact about the customer, and every later component reads a signal that cannot be trusted. The schema is also what constrains the model at call time, so it has to exist before the call is built.

Finalized Approach:
Typed model with provider-constrained structured output: Define the output contract using a typed model such as Pydantic. Generate or derive the provider's structured-output schema from that model, pass it to the LLM provider, and use the same Pydantic model to parse and validate the returned object.

Critical Decision Choices:
* Yes, characteristics are nested under their category object.
* Persona facts are represented as plain strings
* Ambiguity is a separate array of flagged phrases
* Representation of a category stated with no characteristic (must be empty array rather than null).
* Schema must be  closed.
* additionalProperties set to false
* `ExtractedCategory` carries `category_id: int`, assigned in code after the call, not by the extraction model. The provider schema strips this field so the model cannot emit it.
* `AmbiguityFlag` carries `category_id` for `target: "category"` flags (null for characteristic/persona). Also stamped in code; stripped from the extraction provider schema. No `flag_id`.

---

### Sub-component 3: Extraction Instruction and Bucket Separation Rules ####

Goal of Component:
Build the instruction text that makes one call fill the schema and place each piece of the customer's input into exactly one bucket.

Problem It Aims to Solve:
The schema names the buckets but does not define the boundary between them. "I run every morning" can be read as an explicit category request or as a lifestyle fact. Without written separation rules, the same phrase lands in a different bucket on different runs, and the explicit versus inferred priority distinction that Mechanism 4 and Mechanism 6 depend on is set arbitrarily at extraction time.

Three combined Finalized approaches will work together to achieve goal of the component:
1. Rule-only instruction. Written definitions per bucket plus negative rules ("do not map to a category list", "do not add a category the customer did not state").
2. Few-shot instruction. Definitions plus fixed worked input and output pairs covering a rich input, a thin input, an ambiguous phrase, and a negation.
3. Field-level descriptions. Bucket definitions carried inside the schema field descriptions, with a short global rule set in the instruction covering only the cross-bucket boundary.

Critical Decision Choices:
* Definition of "explicit category": An amenity or neighborhood feature that the user directly names or clearly refers to as something they want, prefer, need, avoid, or consider, without requiring the system to infer the underlying category from unrelated context.
* A phrase qualifies as ambiguous when "A phrase is ambiguous when it has two or more reasonable interpretations that would lead to different categories, characteristics, or scopes, and the user's input does not provide enough evidence to select one interpretation confidently.", and Yes, ambiguity can be flagged on the category, the characteristic, persona/lifestyle/situation.
* Handling of negations ("I do not need a gym") and of conditional statements by putting them as lifestyle/situation/persona facts.
* Yes, examples use project amenity vocabulary. Using it pulls the model toward taxonomy mapping, which is locked out of this component.
* There is no upper bound on items per bucket, and what happens when the input names many categories.

---

### Sub-component 4: Constrained Call Execution and Response Validation ####

Goal of Component:
Execute the single extraction call and return either a schema-valid object or a typed failure.

Problem It Aims to Solve:
The response can be truncated, wrapped in surrounding text, missing a required field, or carrying a field outside the contract. Downstream components cannot consume an unvalidated response, and an invalid response with no defined failure path stops the responsibility with no signal any caller can act on.

Finalized Approach:
1. Provider-constrained output. Pass the schema through structured outputs or strict tool use so the response is constrained to the schema at generation time, then validate as a second check. After schema validation, stamp `category_id` by list position and attach it to every category flag; reject the extraction if a category flag does not resolve to exactly one backing explicit entry.

Critical Decision Choices:
* Model selection: We can use OpenAI API as primary API call and Groq API as fallback API call. We need to ensure that we can switch between these two as primary and fallback entity.
* In case of invalid response, the whole response is rejected.
* Failure surface: a raised exception versus a typed error object.
* Category identity is not a third model check. It is programmatic labeling of an already-valid body, then a hard guarantee that every category flag has exactly one `category_id`.

---

### Sub-component 5: Parsed Output Assembly and Handoff Contract

Goal of Component:
Produce the single parsed output object that Component 2A receives as its only input, with a stable identity and a defined signal for the case where extraction did not produce a valid object.

Problem it aims to solve:
This object is the only thing the rest of the responsibility works from, and it is read more than once: Component 2A reads it, and after a clarification round Component 2B attaches the customer's answers to it and 2A reads it again. Without a storage rule, each read reconstructs the object and the two reads can differ. Without a defined failure signal, a failed extraction is indistinguishable from an extraction that legitimately found nothing.

Finalized Approach:
1. In-memory typed return. The validated object is returned directly to the caller, which passes it to Component 2A in the same process.

Critical Decision Choices:
* Parsed object must mutable, allowing downstream components such as Component 2A and 2B to add their results to the same object.
* Empty bucket is represented as an empty array in the handed-off object rather than an omitted field.
* `RequirementInterpretationState.user_responses` is a mapping keyed by `category_id` (default `{}`). `UserResponse` is `{question, options, response}`. Component 2B writes it; Mechanism 1 only provides the empty container and the ids 2B will key on.

---

### Sub-component 6: Test for Mechanism - 1 (Must be designed in a way that it can test the workflow with Dummy LLM Output (DO NOT MAKE API CALL FOR TESTING!!)) 

Goal of Component:
Run a fixed set of input samples with expected bucket assignments through the assembled path and produce a pass or fail per check.

Problem it aims to solve:
The output of this component is the only input the rest of the responsibility receives, and an error here propagates with nothing downstream positioned to catch it. Bucket placement is not verifiable by inspection at run time, and a change to the instruction, the schema, or the model shifts placement without any visible failure.

Finalized Approach:
1. Rubric-based scoring. A second model call scores the produced object against a written rubric per fixture, with a numeric pass threshold.  (For only 1 run!!)

Critical Decision Choices:
* Fixture coverage: rich input, thin input, input naming no category at all, input carrying only persona facts, ambiguous phrasing, negation, and a lifestyle statement that could read as a category request.
* Given that repeat runs on the same input can differ therefore, only one run will be executed for this test.
* The checks gate changes to the instruction and schema
* A category the customer did not state must not appear in the explicit bucket.
* Run artifacts are stored (payload, raw response, validated object) in memory and will be kept in memory during the entire workflow.




                   ************* IMPLEMENTATION DETAILS OF MECHANISM - 1 OF USER REQUIREMENT INTERPRETATION *************

D. Class and Method Blueprint  (Mechanism -1 Implementation Class & Methods)

Class: UserRequirementsInterpretation
File: requirement_interpretation.py
Responsibility: Responsibility 1 entry; holds the ordered providers. Mechanisms 2–9 add methods here.

+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| Method                      | Signature                                                                | Purpose                                               |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| **init**                    | (providers: Sequence[StructuredLLMProvider]) -> None                    | Bind the ordered provider chain                      |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| interpret                   | (raw_input: str) -> RequirementInterpretationState                       | Responsibility entry; sequences mechanisms           |
|                             | [raises: RequirementExtractionError]                                    |                                                      |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| parse_unstructured_input    | (raw_input: str) -> RequirementInterpretationState                       | Mechanism 1 workflow; drives stages 1, 3, 4, 5       |
|                             | [raises: RequirementExtractionError]                                    |                                                      |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| intake_and_assemble_payload | (raw_input: str) -> PayloadRecord                                        | Validate encoding and length, normalize, keep raw    |
|                             | [raises: InputTooShortError, UnsupportedLanguageError]                  |                                                      |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| build_extraction_instruction| (json_schema: dict) -> str                                               | Assemble bucket rules, negative rules, few-shot      |
|                             |                                                                          | pairs                                                |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| execute_and_validate        | (payload: PayloadRecord, instruction: str) -> ExtractedRequirements     | Try llm providers in order, validate, stamp category_id |
|                             | [raises: ExtractionProviderError, ExtractionValidationError]            |                                                      |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+
| assemble_handoff            | (payload: PayloadRecord, extracted: ExtractedRequirements)               | Pair payload and buckets as the mutable handoff      |
|                             | -> RequirementInterpretationState                                       |                                                      |
+-----------------------------+--------------------------------------------------------------------------+------------------------------------------------------+



--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------*************** Mechanism - 2 , Responsibility - 1 of feature Deep Search ******************------------------------------------
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# Mechanism 2 (Explicit Category Resolution & Global Requirement Sufficiency Gate) ,Responsibility 1 (User's Requirement Interpretation)

## Process Flow — Component 2A: Category Scope & Ambiguity Resolution

Locked constraints carried into this breakdown:

These are fixed at the component level and are not reopened by any sub-component below.

Input is the RequirementInterpretationState produced by Mechanism 1 (payload, extracted buckets with extraction-owned `category_id` on every explicit category and on every category flag, and user_responses defaulting to an empty mapping keyed by `category_id`).
Operation 1 (taxonomy mapping) always runs. Operation 2 (ambiguity resolution) runs only when user_responses is populated.
Mapping is constrained to the maintained amenity-category taxonomy. The call selects an existing node. It does not invent, rename, split across, or return anything outside the taxonomy.
The mapping model echoes `category_id` only. It does not echo category names. An unmapped category becomes an AmbiguityFlag with target: "category" and that same `category_id`; phrase and characteristics are looked up from `explicit_categories[category_id]`. It is not dropped.
Mechanism-1 flags whose target is not "category" are carried into ambiguity_flags. Category flags after Operation 1 come from `unmapped_category_ids` (one flag per id).
Operation 2 processes only flags with target: "category", paired with `user_responses[category_id]`. Flags with target: "characteristic" pass through unchanged.
Once user_responses is present, every category flag exits Operation 2 as a resolved taxonomy entry (confidently, or mapped to the nearest fitting node). Zero category flags survive the second pass.
Output is a new ResolvedRequirements object with four fields: payload (carried unchanged), resolved_explicit_categories, ambiguity_flags, persona_facts (carried unchanged).
This component does not count categories, apply the sufficiency threshold, generate clarifying questions, or write user_responses. Those belong to the router and Component 2B.

Sub-components
Input State and Flag Contract Preparation
Output Contract Definition
Taxonomy Provision and Access
Operation 1: Taxonomy Mapping and First-Pass Flag Set
Operation 2: User-Response Gate and Category-Flag Resolution


### Sub-component 1: Input State and Flag Contract Preparation

Goal of Component:
Extend the mechanism-1 data contracts so 2A can read the gate signal and can carry, create, and resolve category flags. This covers `user_responses` on the RequirementInterpretationState (default empty, keyed by `category_id`) and `category_id` on AmbiguityFlag for category flags.

Problem It Aims to Solve
2A branches on user_responses and works over AmbiguityFlag objects. If the state has no user_responses field, the conditional gate has nothing to read. If category flags lack `category_id`, 2A cannot pair a flag with its answer without string matching — the paraphrase/mismatch path this pre-requisite removes.

Finalized Approach:
Additive field extension. `user_responses` is keyed by `category_id`. `AmbiguityFlag.category_id` is stamped by Mechanism 1 for category flags. No `flag_id`.


Ambiguity fields Meaning:
phrase — the exact ambiguous phrase from the customer.
target — whether the ambiguity concerns a category or characteristic.
category — the category associated with the phrase, when known.
characteristic — the characteristic associated with the phrase, when known.
category_id — the extraction-owned identity of the backing explicit category, when target is "category"; null otherwise.



Critical Decision Choices
The container type for user_responses. Component 2B writes a mapping keyed by `category_id` (not flag phrase). 2A looks up `user_responses[category_id]`.
Decision: `dict[int, UserResponse]` keyed by `category_id`, not a list and not phrase-keyed.
2. Which AmbiguityFlag fields are required versus optional, given that a mechanism-1 flag may arrive with category or characteristic null.
    1. Decision: phrase, target, category, characteristic remain as before (category/characteristic default None). `category_id` is required to be set on every `target: "category"` flag; null on characteristic/persona flags.
4. Whether mechanism-1 is updated to populate phrase, target, category, characteristic, and category_id on every flag it emits.
    1. Decision: Yes. Identity is assigned in code after extraction, not by the extraction model. 



### Sub-component 2: Output Contract Definition

Goal of Component:
Define the ResolvedRequirements object and the ResolvedCategory entry type that Operations 1 and 2 populate and that the router reads.

Problem It Aims to Solve:
Operation 1 and Operation 2 both produce resolved category entries and a flag set, and both must write into a fixed shape. Without a declared output contract, each operation invents its own entry structure and the router receives an object whose fields it cannot depend on. The ResolvedCategory entry type in particular is needed before the operations run, because both operations create entries of that type.

Finalized Approach:
Typed model classes. Declare ResolvedRequirements and ResolvedCategory as typed model classes (Pydantic or equivalent), generating validation from the type definitions. ResolvedRequirements would become the part of the RequirementInterpretationState (which is essentially a state of the workflow)


Critical Decision Choices:
Yes, Field set on ResolvedCategory: `category_id` (copied from the echoed mapping/resolution id, not re-derived), `taxonomy_node`, `raw_name`, and `characteristics` are fixed by the component spec. Whether the entry also carries provenance (whether it came from Operation 1 confident mapping, Operation 2 confident resolution, or Operation 2 nearest-node fallback) is decided here.
Yes, Characteristic in ResolvedCategory is copied by value from the mechanism-1 flag or category, given the locked rule that this component does not modify characteristics.
In case of ResolvedRequirements, the same object is updated in place across the two passes.


### Sub-component 3: Taxonomy Provision and Access

Goal of Component:
Make the maintained amenity-category taxonomy available to the mapping call and the nearest-node fallback in a consumable, node-identified form.

Problem It Aims to Solve:
Both operations select a taxonomy node, so both need the taxonomy present at call time with stable node identifiers. Without a defined access path, the taxonomy gets embedded ad hoc in each prompt, node identifiers drift between calls, and a taxonomy change requires editing the mapping logic. The taxonomy is also the boundary that keeps the mapping constrained, so its representation determines whether a returned node can be checked as a real node.

Finalized approach:
Inline full taxonomy. Render the entire taxonomy into the prompt as a flat or nested list of nodes with identifiers, suitable when the taxonomy is small enough to fit the context.

Critical decision choices:
1. Full taxonomy vs. retrieved candidate subset
	Decision: Full taxonomy, always.


### Sub-component 4: Operation 1 — Taxonomy Mapping and First-Pass Flag Set    (SUB - COMPONENT 4 )


 Goal of Component

For each raw category from the mechanism-1 extraction, select a single taxonomy node using the category name, its characteristics, and persona context. Convert any category that cannot be confidently mapped into a category flag, merge in the carried mechanism-1 flags, and produce the resolved-category entries plus the working ambiguity_flags set.

 Problem It Aims to Solve

A raw category label alone does not identify a real-world scope ("grocery" and "convenience store" overlap but differ). Downstream mechanisms need a taxonomy node, not a raw string. A category the model cannot place must be recorded as a flag so 2B can ask about it, rather than being dropped or guessed. This operation is the always-run core of 2A and produces the object the router inspects on the first pass.


Finalized Approach

Single LLM call with sorting output. One call receives all labeled explicit categories together with the full mechanism-1 output and the full amenity-category taxonomy. The model sorts each `category_id` into one of two arrays: resolved_categories (confidently mapped as `{taxonomy_node, category_id}`) or unmapped_category_ids (could not map). Constrained decoding on the taxonomy_node field prevents out-of-taxonomy returns for resolved entries. After the call, `category_id` is kept on each `ResolvedCategory`, `raw_name` and characteristics are attached by looking up `explicit_categories[category_id]`, unmapped ids become category flags carrying that id, non-category mechanism-1 flags are merged, and persona facts and payload are copied unchanged to assemble the full ResolvedRequirements object.


 Critical Decision Choices


 1. Call Granularity

One call for all categories. The model sees the full set of raw categories together, allowing cross-category context to inform each mapping. A single call is cheaper and produces one response to validate. Partial failure (one category invalid in an otherwise valid response) is handled at the post-call assembly step, not by retrying individual categories.


 2. What the Model Receives

The full mechanism-1 output (explicit_categories already labeled with `category_id`, characteristics, ambiguity_flags, persona_facts, and payload) plus the full maintained amenity-category taxonomy with node identifiers.

The prompt explicitly instructs the model that the richer context (persona facts, characteristics) is provided for understanding what the user wanted or intended to say for their explicit categories — not for inferring new categories. The model must not add a category the customer did not state.


 3. What the Model Returns — Schema Shape

Two arrays, nothing else.

**resolved_categories** — one entry per confidently mapped category:

| Field | Constraint |
|---|---|
| `taxonomy_node` | Constrained to valid taxonomy node identifiers only. |
| `category_id` | The id of the explicit category being mapped, echoed from the input. The model must not invent an id or return a name. |

**unmapped_category_ids** — the `category_id` of every explicit category the model could not confidently place. Empty list when every category mapped.

Every extracted `category_id` appears in exactly one of the two arrays. The model does not return names, characteristics, persona facts, payload, or AmbiguityFlag objects. Those are handled programmatically.


 4. How the Model Signals Low Confidence

The model places the category's `category_id` into `unmapped_category_ids` instead of `resolved_categories`. There is no sentinel value, no confidence score, and no secondary field. The sorting decision itself is the confidence signal — if it is in resolved_categories, the model was confident; if it is in unmapped_category_ids, it was not.


 5. Characteristics Handling

Attached programmatically after the call, not by the model. The model returns only `category_id` and `taxonomy_node` for each resolved entry.

After the call, each resolved entry's `category_id` is copied onto the `ResolvedCategory` and looked up in the mechanism-1 extraction's `explicit_categories` to copy `name` (as `raw_name`) and the characteristics list onto the entry.

Paraphrase and match-failure are structurally impossible because no name string is ever echoed by the mapping model.


 6. Mechanism-1 Ambiguity Flag Merge

Programmatic, post-call. Non-category mechanism-1 flags (characteristic, persona) are copied unchanged. Category flags are rebuilt from `unmapped_category_ids` so each `category_id` appears at most once. If Operation 1 maps a category that Mechanism 1 had flagged, that category enters `resolved_explicit_categories` and no category flag remains for it.


 7. Persona Facts and Payload

Copied unchanged from the `RequirementInterpretationState` into the `ResolvedRequirements` object. Programmatic, post-call. The model does not return these and this component does not modify them.


 8. Post-Call Assembly Sequence

After the call returns and is validated, the following steps run in order:

1. **Attach identity, name, and characteristics:** For each entry in the model's resolved_categories — copy `category_id` from the mapping, look up `explicit_categories[category_id]`, copy name and characteristics onto the entry to produce a full `ResolvedCategory`.
2. **Carry non-category mechanism-1 flags.**
3. **Create category flags** from `unmapped_category_ids`, each carrying that `category_id` and `phrase` from the backing explicit entry.
4. **Copy persona facts** from the state unchanged.
5. **Copy payload** from the state unchanged.
6. **Assemble** the full `ResolvedRequirements` object from steps 1–5.


 9. Coverage Handling

If the model returns an unknown `category_id`, duplicates an id across the two arrays, or omits an extracted id from both arrays, the Operation 1 body is a validation failure. There is no paraphrase-to-flag conversion, because names are not in the wire contract.



# Sub-component 5: Operation 2 — User-Response Gate and Category-Flag Resolution


 Goal of Component

Branch on whether `user_responses` on the `RequirementInterpretationState` is populated. When it is empty, skip resolution and leave the flag set from Operation 1 as final. When it is present, resolve every `target: "category"` flag against its paired user response and surrounding context, mapping to a taxonomy node confidently where the response gives enough evidence and to the nearest fitting node where it does not, so no category flag survives. Leave `target: "characteristic"` flags untouched.


 Problem It Aims to Solve

A category-level flag ("a place to get my shopping done") cannot be taxonomy-mapped until the customer clarifies. After a clarification round, the paired responses provide that evidence, and this operation converts the flags into resolved entries. Without the gate, a first pass with no responses would attempt resolution with nothing to resolve against. Without the nearest-node fallback, a still-vague response would leave a category flag in place, and the router would loop with no path to clear.


 Finalized Approach

Single LLM call with paired input and two-stage judgment. One call receives all `target: "category"` flags from the working flag set, each paired with `user_responses[category_id]`, as a structured list of {flag, user_response} pairs. The model performs two judgments per flag in a single pass: first, whether the user response provides enough evidence for a confident taxonomy mapping; second, if not, which taxonomy node is the nearest fit. Every flag exits with a taxonomy node — either confident or nearest-node — echoing the `category_id` it was handed. After the call, name and characteristics are attached from `explicit_categories[category_id]`, resolved entries are added to the existing `ResolvedRequirements` object, and resolved flags are removed from `ambiguity_flags`.


 Critical Decision Choices


 1. Gate Condition

Check whether `user_responses` on the `RequirementInterpretationState` is populated. If empty, this entire operation is skipped — the flag set from Operation 1 is final and the `ResolvedRequirements` object passes to the router unchanged. If present, proceed with resolution.


 2. Call Granularity

One call for all category flags. The model receives every `target: "category"` flag with its paired user response as a structured list of {flag, user_response} pairs. The pairing is given explicitly in the input — the model does not look up or match responses itself. Responses are returned in the same order as the input list.


 3. Two-Stage Judgment in a Single Call

The model performs both the confident-mapping and nearest-node judgments in one pass per flag. For each {flag, user_response} pair, the model returns:

| Field | Constraint |
|---|---|
| `taxonomy_node` | Constrained to valid taxonomy node identifiers only. Always filled — the model's best pick regardless of confidence. |
| `category_id` | The id of the category flag being resolved, echoed from the input. Must not invent an id or return a name. |
| `provenance` | One of: `"confident"` (user response gave enough evidence to map clearly) or `"nearest_node"` (user response was still insufficient, model selected the nearest fitting node). |

No category flag survives this operation. Every flag exits as a resolved entry with a taxonomy node.


 4. What the Model Receives

The full context available at this point:

- The list of {flag, user_response} pairs to resolve (from the working `ambiguity_flags` filtered to `target: "category"`, each paired with `user_responses[category_id]` on the state).
- The full mechanism-1 output (explicit categories, characteristics, persona facts) — for understanding what the user wanted, not for inferring new categories.
- The Operation 1 resolved categories already in the `ResolvedRequirements` object — so the model sees what was already mapped and avoids duplicate or conflicting nodes.
- The full maintained amenity-category taxonomy with node identifiers.

The prompt explicitly instructs the model that mechanism-1 context and Operation 1 results are provided for understanding and avoiding conflicts — not for adding categories the customer did not state.


 5. What the Model Does Not Return

The model does not return characteristics, persona facts, payload, mechanism-1 ambiguity flags, or `target: "characteristic"` flags. Those are handled programmatically.


 6. Characteristics Handling

Attached programmatically after the call, same as Operation 1. Each resolved entry's `category_id` is copied onto the `ResolvedCategory` and looked up in mechanism-1's `explicit_categories` for `raw_name` and characteristics.

Every `target: "category"` flag in the working set was originally an explicit category from mechanism-1 that Operation 1 could not map. The raw category never left `explicit_categories`. The id lookup always finds the backing entry.


 7. How Operation 2 Merges into Operation 1's Output

Update in place on the existing `ResolvedRequirements` object that Operation 1 produced:

1. **Add resolved entries:** For each entry the model returned — copy `category_id`, attach name and characteristics from `explicit_categories[category_id]`, then append the full `ResolvedCategory` (with provenance) to the existing `resolved_explicit_categories` array.
2. **Remove resolved flags:** Remove every `target: "category"` flag from `ambiguity_flags`. After this operation, zero category flags remain — only `target: "characteristic"` flags (if any) survive.
3. **No other fields change:** `persona_facts`, `payload`, and `target: "characteristic"` flags are untouched.


 8. Post-Operation State

After Operation 2 completes, the `ResolvedRequirements` object contains:

| Field | Content after Operation 2 |
|---|---|
| `resolved_explicit_categories` | All entries from Operation 1 (confident first-pass mappings) plus all entries from Operation 2 (user-response-driven mappings, each with provenance). |
| `ambiguity_flags` | Only `target: "characteristic"` flags remain. Zero `target: "category"` flags — guaranteed by the nearest-node fallback. |
| `persona_facts` | Unchanged from mechanism-1. |
| `payload` | Unchanged from mechanism-1. |

This is the object the router inspects on the second pass. Because zero category flags remain, the router always clears to Mechanism 3.






























### 2. Amenity discovery 

**Responsibility:** Find the actual amenities that exist within the defined neighborhood.

This includes:

* Searching by amenity category.
* Applying the user's geographic boundary.
* Producing candidate amenities.

**Boundary:**
Its output is essentially:

> "These are the candidate gyms/restaurants/parks within the defined area."

It should **not decide whether those amenities satisfy the user's preferences**.

---

### 3. Amenity data acquisition

**Responsibility:** Collect the factual information needed about each candidate.

This includes:

* Name
* Website
* Address
* Baseline metrics
* User-specific metrics
* Deeper information when required
* Information from different sources/tools

This is where your Google Maps, website extraction, web search, etc. belong conceptually. Your environment explicitly says that different tools provide different kinds and depths of information. 

**Boundary:**
Its output should be **facts and metrics**, not conclusions.

---

### 4. Accessibility evaluation

I would consider this a **separate responsibility**, because it answers a different question from amenity discovery.

**Responsibility:** Determine how accessible an identified amenity actually is.

For example:

> Gym A → walking → 8 minutes → specific route

This is different from:

> Gym A exists 600 m away.

Your own problem explicitly distinguishes route-based accessibility from geographic distance. 

**Boundary:**
It takes an identified amenity and produces accessibility data. It does not decide whether the gym is a good match.

---

### 5. Candidate selection

**Responsibility:** Determine which amenities within each category are worth presenting.

This includes:
* Matching user-specified characteristics.
* Considering reasonable alternatives.
* Removing unnecessary duplicates or excessive results.
* Selecting a representative set.

This is different from discovery: **discovery finds what exists; selection decides what is relevant enough to continue with.**

Your workflow explicitly has this narrowing step after the deeper search. 

---

### 6. Assessment / judgment

This is another very clear boundary.

**Responsibility:** Use the collected facts and metrics to determine how well each category or amenity satisfies the user's requirements.

For example:

> Facts: Gym A is 700 m away, 4.6 rated, open 24 hours.
> Assessment: Gym A is a strong match for the user's requirement for a nearby 24-hour gym.

The assessment should remain separate from the facts, while retaining the facts it was based on. This separation is explicitly part of your problem definition. 

---

### 7. Presentation

**Responsibility:** Convert the resulting information into the structure the user should see.

This includes:

* Organizing by amenity category.
* Organizing by metric.
* Adjusting depth.
* Phrasing results against the user's requirements.

This should **not perform new research or make new judgments**.





























