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

1. User's Requirement interpretation (Responsibility of the feature)

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
Single-pass structured extraction: one LLM call with a fixed output schema that extracts categories, characteristics, ambiguity flags, and persona/lifestyle/situation facts together. At this stage, we are not mapping the categories to our amenity-categories list. We just want to extract the amenities which user has mentioned in their response.


Mechanism 2 — Explicit Category Resolution & Global requirement sufficiency Gate

Component 2A: Category Scope & Ambiguity Resolution

Goal of Component: Map every extracted category to its correct real-world scope based on defined amenity-category taxonomy.
Problem It Aims to Solve: A category label alone can silently include or exclude adjacent real-world entities ("grocery" vs. "convenience store"), and an unresolved vague category/ characteristic ("good gym") produces a specification that looks complete but is quietly evaluating the wrong thing.

Approach:
Context-Aware Taxonomy Mapping:
Use the user's specification and relevant surrounding context to identify the intended amenity, while constraining the resolved amenity to the maintained amenity taxonomy. The LLM interprets ambiguous or indirect references and maps them to the most appropriate taxonomy node rather than inventing new amenity categories.

This gives you the best of both approaches:
Taxonomy → Gives consistency and control
Context → Gives understanding and flexibility

Critical Decision Choices:
Generic: what reference scope definition counts as "correct," so resolution is checkable rather than a vibe.
	Decision: Resolution for ambiguous category must be available in the Taxonomy. And resolution for characteristic can be evaluated by looking at the context of the user.



ROUTER: Counts the number of categories resolved and if it finds that they are less than the set threshold then it triggers the Component 2B otherwise it refers the workflow to the Component 3.

Component 2B Global Requirement Sufficiency Gate (runs only if category resolution has resulted in less categories than mentioned in threshold)

Goal of Component: Immediately after category resolution, determine whether the customer's combined input — explicit mentions plus persona/situation/lifestyle facts — contains enough raw material to get number of categories more than the threshold set for it so, that we can run the rest of the responsibility meaningfully at all. If not, produce and pose a targeted clarifying question about ambiguous categories or additional categories grounded in the information that is already provided by the user.

Problem It Aims to Solve: If the input is close to empty (no categories, no persona detail), continuing anyway produces a specification built on fabricated assumptions dressed up as personalization.

Approach:
Rule-based clarification gate with instruction-grounded question generation:
Define explicit minimum thresholds (e.g., fewer than 3 distinct persona/situation facts or fewer than 3 categories) to determine when clarification is needed. When triggered, use an LLM to generate dynamic questions grounded strictly in the user’s existing instructions. Questions should expand, clarify, or add detail to information the user has already provided, rather than introduce assumptions about unstated preferences or needs. Core principle would be "Ask to deepen what the user said, not to speculate about what they might want."

Decision: Trigger clarification only when:
	1) The number of explicitly specified categories resulted after category resolution is below the defined minimum threshold of 3
	
When customer responds:
Make those responses part of the customer parsed output object as "User Responses". Now, this response will go back to the Component 2A so, that category resolution can work again with better contextual information in the light of the user responses.


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




