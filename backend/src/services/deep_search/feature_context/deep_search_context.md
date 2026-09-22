# Google Places API Integration with Deep Search feature

## Hierarchy in deep search feature:
1. Listings & their Quality
2. Apartment Amenities
3. Neighborhood Quality
Essentially Deep search is just going to be an orchestrator. And we can consider its responsibilities as feature itself and they will be orchestrated by Deep Search.


# Problem Context of the Neighborhood Quality aspect of the feature:
## Overall Feature Problem:
The feature needs to determine whether the neighborhood surrounding an apartment meets the user's stated preferences by identifying relevant amenities and providing reliable information about their proximity, accessibility, characteristics, and quality. The information must be sufficiently specific to the user's requirements at the required level of depth rather than presenting a generic list of nearby amenities, while distinguishing factual information and information in the form of metrics about each amenity from assessments derived from that information.


## User:
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


## Environment:
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

## Problem relevance:
If amenity information isn't matched to what the user actually cares about, at the depth and characteristic level he cares about, and isn't clearly separated from the judgment drawn on top of it, he's left to manually re-derive relevance and quality himself from a generic report, which defeats the purpose of the feature responsibility doing that evaluation for him, and undermines his ability to trust the assessment when deciding whether a listing's surroundings actually fit his needs.


## Actual Problem Statement:
The feature must first identify amenities within a user-defined radius of the listing, covering the amenity categories the user explicitly specified at full priority and a smaller, fixed set of common categories he did not specify, based on the understanding of his explicit and hidden requirements. For each identified amenity (in each category), it must retrieve a fixed baseline set of metrics using whichever available tool is best suited to that data (Google Places New API) and extending to deeper, page-level detail only where the user's stated need calls for it using additional tools like LLMs, Diffbot extractor and Parallel Web Search. For every amenity, it must compute travel-based accessibility (route, mode, time), not straight-line distance alone. Within each category, it must narrow results to a representative set, keeping only amenities that match a user-specified characteristic or a reasonably close alternative where such criteria were given, rather than returning every instance found. From this factual data, it must produce an assessment for every amenity (of every category), specified or baseline, keeping that assessment structurally separate from the underlying facts while carrying the specific facts it was derived from. Finally, the output must be organized by amenity category and metric, with depth scaled to how much the user specified about that category, and each result phrased against the user's stated requirement rather than as a generic summary.


## Workflow of the Feature:
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


## Responsibilities of the feature:

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


### Problem Context of User's requirements interpretation:
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


#### Actual Problem statement:
This responsibility must first parse the customer's stated requirements and instructions to come up with the discrete amenity categories, resolving each to its correct real-world scope and, where a stated characteristic for any category of amenity is vague or open to more than one meaning, resolving it to a single reasonable interpretation, and capturing the underlying reason behind why each explicit category matters to him. These explicit categories and their captured reasoning are treated as fixed, top priority input in the context of customer's described persona, situation, and lifestyle,. Next, based on the customer's described persona, situation, and lifestyle, it must infer additional categories and their characteristics he did not explicitly state, appended below the explicit set as lower-priority, probabilistic additions that cannot compete with or dilute what was explicitly stated. For every category, explicit or inferred, it must assign a depth of information (metrics, factual information, characteristics) to the surface, based on how much the customer specifications about that particular category or if not specified then understanding what level of depth a category amenity would require to evaluate it, applying this depth-assignment logic the same way across all categories rather than case by case. Finally, for every category, it must define the specific metrics and factual points, category-appropriate rather than drawn from one fixed template, that are sufficient to judge whether an amenity actually serves the customer's underlying purpose for wanting that category, not merely to describe that the amenity exists. The output of this responsibility is this specification per category (reason, priority, depth, metrics) and nothing beyond it, no search or retrieval of amenities happens here.

Filter check (problem relevance): every clause traces back to producing an accurate, appropriately prioritized, sufficiently deep specification per category, since anything wrong or missing here propagates uncorrected into search, retrieval, and the final judgment. Nothing here performs search or retrieval, which belongs to a later responsibility.


##### Implementation (Workflow/Process flow of the responsibility) Mechanisms of the User's Requirement Interpretation:
Process Flow — "User's Requirement Interpretation" Responsibility

Scope reminder: everything below stops at producing a per-category specification (reason, priority, depth, metrics). Nothing here searches, retrieves, or scores an actual amenity — that starts in the next responsibility, which consumes this one's output as its only input.

Mechanisms identified
1. Unstructured Input Parsing (prerequisite)
2. Explicit Category Resolution
3. Router --> Global Requirement Sufficiency Gate --> Explicit Category Resolution
4. Persona-Driven Category Inference
5. Depth Assignment
6. Category-Specific Metric & Fact Definition



# Mechanism 1 — Unstructured Input Parsing
## Component: Requirement & Persona Extraction

Goal of Component: Convert the customer's raw natural-language input into a structured intermediate representation that keeps three things separate: (a) explicit category (b) category characteristics, (c) phrases flagged as ambiguous, (d) general persona/situation/lifestyle facts.

Problem It Aims to Solve: Every later component needs to know whether it's looking at "something the customer asked for" or "background about who he is" — if these get conflated at extraction time, reasoning capture and inference downstream have no reliable signal to work from.

### Approach:
Single-pass structured extraction: one LLM call with a fixed output schema that extracts categories, characteristics, ambiguity flags, and persona/lifestyle/situation facts together. At this stage, we are not mapping the categories to our amenity-categories list. We just want to extract the amenities which user has mentioned in their response. The extraction model does not emit identifiers.

Extraction-owned category identity (`category_id`):
When Mechanism 1 assembles `ExtractedRequirements`, each `explicit_categories` entry is labeled with a stable `category_id` in code, by list position. Flagging a phrase does not remove it from its bucket, so every `target: "category"` flag has exactly one backing explicit entry; that flag is stamped with the same `category_id` in the same assembly pass. A category flag that does not resolve to exactly one backing entry is a validation failure, not a defensive workaround. There is no separate `flag_id`. This id is the single key for the Mechanism 2 clarification loop (`user_responses`, 2B questions, 2A Operation 2). Names stay on the extracted entry; later models echo ids only.


## Process Flow — Component: Requirement & Persona Extraction

Locked constraints carried into this breakdown. These are fixed at the component level and are not reopened by any sub-component below.

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

## Class and Method Blueprint (Mechanism 1)

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

---

# Mechanism - 2  

## Component 2A: Category Scope & Ambiguity Resolution

### Goal of Component

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


### Problem It Aims to Solve

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


### Approach: Context-Aware Taxonomy Mapping

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


### Critical Decision Choices


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

## Router: Category Resolution Check

### What it is
A conditional check that is one step inside **Mechanism 2** (alongside 2A and 2B), sequenced by a Mechanism-2 orchestrator. It is not a component: no LLM call, no transformation, no output object. After each 2A pass it reads the workflow state, owns the pass counter, and makes one binary branch decision.

### Input
The full `RequirementInterpretationState`. It reads `state.resolved.ambiguity_flags` to decide and forwards the **whole state** onward, so 2B can write to it and 2A's second pass can read it.

### Decision
Let `has_category_flag = any(f.target == "category" for f in state.resolved.ambiguity_flags)`.

| Condition | Branch |
|---|---|
| `has_category_flag` is True | Forward state to **Component 2B** |
| `has_category_flag` is False (only `characteristic` and/or `persona` flags, or none) | Forward state to **Mechanism 3** |

`characteristic` and `persona` flags never route to 2B; both fall through to Mechanism 3.

### Loop constraint (enforced structurally)
The router owns `state.category_resolution_passes`, incremented each time it inspects a fresh 2A output.

1. **Pass 1** (`user_responses` empty): category flags may exist → route to 2B.
2. **Pass 2** (`user_responses` populated by 2B): 2A Operation 2 guarantees zero surviving category flags — the customer cannot skip a question, so every category flag has a response keyed by its `category_id`, and each resolves confidently or via nearest-node. Router clears to Mechanism 3.

Hard cap: the router MUST NOT route to 2B when `category_resolution_passes >= 2`; it routes to Mechanism 3 unconditionally. This is a defensive guard; the guarantee should make it unreachable.

---

## Component 2B: Category Clarification Questions

### Goal of Component
Three ordered operations, each depending on the previous completing:

1. **Generate questions (LLM):** one clarification question (with options) per category flag, in a single batched call.
2. **Present and collect (CLI):** show each question and its options in the CLI and block until the customer provides a response. A response is mandatory.
3. **Write to state:** write each `{question, options, response}` into `state.user_responses`, keyed by the category flag's `category_id`.

### Problem It Aims to Solve
When 2A's first pass leaves category flags unresolved, those categories have no taxonomy mapping and cannot enter `resolved_explicit_categories`. 2B is solely responsible for generating grounded clarification questions, collecting the customer's answers, and handing them to 2A via the state under each flag's `category_id`. What 2A does with those answers afterward (confident mapping vs. nearest-node fallback) is 2A's concern, not 2B's.

### Approach: Instruction-Grounded, Batched Question Generation
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

### Critical Decision Choices

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

#### Part 3 — Before/After state and residual gaps

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


### Sub-component 5: Operation 2 — User-Response Gate and Category-Flag Resolution


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


## Process Flow — Router & Component 2B (User Feedback & Category Resolution)


### Sub-component 1: Pass-counted category-flag branch
Goal of Component
After 2A has written state.resolved, increment category_resolution_passes and emit one branch: Component 2B or Mechanism 3.

Problem It Aims to Solve
2A pass 1 can leave target: "category" flags that have no taxonomy node. Without an inspect that reads those flags and applies the two-pass cap, the workflow has no defined next step: category flags never reach clarification, characteristic or persona flags are sent to 2B, or 2B runs again after the second 2A pass.
Finalized approach:
Response: You can choose the approach which is most appropriate given the context of our problem. And you can also address the decision choices that are still open. However, you need to provide the reaosning for the approach you will finalize. 

Parent constraints (do not reopen):
has_category_flag = any(f.target == "category" for f in state.resolved.ambiguity_flags).
Characteristic and persona flags never route to 2B.
Hard cap: do not route to 2B when category_resolution_passes >= 2.
Field name is state.category_resolution_passes.
The whole state is forwarded.


### Sub-component 2: Clarification wire contract
Goal of Component
Declare the closed shape of the question-generation call: ClarificationQuestion, ClarificationResult, and CLARIFICATION_SCHEMA_NAME, so a provider body can be constrained and validated.

Problem It Aims to Solve
The batched call has nothing to constrain against and nothing to validate against. Questions cannot be joined to flags by category_id if the model is free to return an unbounded object.
Finalized approach:
Pydantic models, schema derived. Define ClarificationQuestion and ClarificationResult as Pydantic models with extra="forbid". Derive the provider JSON schema from those models and close it the same way Mechanism 1 and 2A close theirs. CLARIFICATION_SCHEMA_NAME is the name the provider echoes.
Parent constraints (do not reopen):

ClarificationResult:

Field	Type	Content
questions
list[ClarificationQuestion]
One entry per submitted category flag
ClarificationQuestion:

Field	Type	Content
category_id
int
Identity of the category flag, echoed from input
category
str
Flagged category phrase, for display and grounding
question
str
The clarification question
options
list[str]
Candidate interpretations to show the customer

Critical Decision Choices:
Minimum and maximum length of options : Must be always 5 options in total, one of them would always be "other"
Whether questions order must match the submitted flag order, or matching is by category_id only: matching is by category_id only
Whether questions may be empty (2B is not invoked when there are zero category flags; the contract still has to say what an empty list means if it appears): I don't think this matter because router will never invoke the 2B when list will be empty


### Sub-component 3: Clarification instruction assembly
Constants module. Task statement, rules, negative rules, and few-shot pairs live as module-level strings. A build_* function concatenates them with the schema and the serialized flags, the same pattern as category_resolution_instruction.py for 2A.

Goal of Component
Produce one instruction string the generation call sends with the schema: all target: "category" flags plus grounding from state.resolved (resolved_explicit_categories, payload, persona_facts, ambiguity_flags).

Problem It Aims to Solve
Without that instruction, the model is not told that a question exists only to clarify which amenity-taxonomy node the stated category maps to. Questions can introduce unstated needs, bundle two flags, or ask about characteristic or persona flags.

Critical Decision Choices:
Whether the maintained taxonomy node list is inlined in this prompt (2B asks what the category maps to; it does not select a node): No, we do not need that in 2B prompt.
How many few-shot pairs to include: 2 
How the category phrase is shown next to category_id in the input block: ID and phrase together

Parent constraints (do not reopen):

Ground questions in the customer's wording and existing state.resolved context.
Do not introduce assumptions about unstated needs.
Purpose is taxonomy-scope clarification, not preference, discovery, or a new-requirement prompt.
One question per category flag. No bundling.
Do not generate questions for characteristic or persona flags.


### Sub-component 4: Constrained batched question generation

Goal of Component
One provider call returns a validated ClarificationResult that covers every submitted category_id, or a typed failure. The call does not write user_responses or resolved.

Problem It Aims to Solve
Without this call, 2B has no questions to present. Without a coverage check, a valid-looking body can omit a flag, duplicate an id, or invent an id, and the CLI cannot key answers for 2A Operation 2.

Finalized approach:
Validate body, then check ids. Reuse _call_providers with CLARIFICATION_SCHEMA_NAME. Parse the body into ClarificationResult. Reject the whole body if schema validation fails. Then require that the set of returned category_id values equals the set of submitted category-flag ids.
Additional requirement: If the body validates but coverage fails, send the same schema and instruction once more. A second coverage failure is a typed validation exit. Total provider failure is still a typed provider exit.

Critical Decision Choices:
Whether provider failure uses a new ClarificationProviderError or reuses CategoryMappingProviderError: ClarificationProviderError 
The stage name on those errors: Op2 for Questions generation stage
Whether unknown, duplicate, or missing category_id is a validation error or a provider error: It is a validation error
Rename CLARIFICATION_SCHEMA_NAME to CLARIFICATION_QUESTIONS_SCHEMA_NAME

Parent constraints (do not reopen):
Reuse self._providers and _call_providers.
Use CLARIFICATION_SCHEMA_NAME.
Total provider failure is a typed error.
One batched call for all category flags, not one call per flag.
Do not write resolved.*.


### Sub-component 5: CLI present, collect, and persist
Goal of Component
For every generated ClarificationQuestion, collect a non-empty customer answer and write UserResponse {question, options, response} to state.user_responses[category_id].

Problem It Aims to Solve
A question that is printed and not stored leaves user_responses empty for that category_id. 2A Operation 2 then has no paired answer. The Router's second-pass guarantee (every category flag has a response, no skip) does not hold.

Finalzed approach:
One stdin prompt per question. Print that question and its options. Read one line. If the line is empty or whitespace, print again. When a non-empty line is read, write user_responses[category_id] and move to the next question.
Additional requirements: Print each question with numbered options. The customer types an index. An out-of-range or empty entry is re-prompted. The stored response is the selected option string (or the index, depending on the open decision below).

Critical Decision Choices:
Prompt wording around each question: Phrase with wording that help us understand this instruction
Whether the stored response must equal one of options, or any non-empty string is stored: stored response must equal one of options until others option is selected for which user can type anything
CLI encoding and how non-ASCII answers are read: Not relevant as of now.

Parent constraints (do not reopen):
Synchronous and blocking. The workflow does not proceed until each question is answered.
Blank or empty answers are re-prompted and never stored.
Key is category_id, not phrase matching.
The only write is state.user_responses.
resolved.resolved_explicit_categories, resolved.ambiguity_flags, resolved.persona_facts, and resolved.payload stay unchanged.
category_resolution_passes is not incremented here (the Router increments on its next inspect).


### Sub-component 6: Mechanism-2 loop sequencing
Goal of Component
For one request: run 2A pass 1, run the pass-counted branch, then either enter 2B and 2A pass 2 and branch again, or go to Mechanism 3. Component 2B runs at most once.

Problem It Aims to Solve
interpret currently runs parse then 2A only. The branch and 2B have no invoker. Pass 2 would not reuse state.resolved, and 2B could be called with no cap.


Critical Decision Choices:
Pass 2: user_responses filled by 2B → skip Op1, run Op2 on the object already on the state.
Whether Mechanism 3 is invoked here or the state is returned to the feature class for the next mechanism: state is returned to the feature class for the next mechanism

Parent constraints (do not reopen):

Pass 2 reuses the existing state.resolved. It does not rebuild it from scratch.
Operation 1 is skipped on pass 2. Operation 2 runs over surviving category flags paired with user_responses[category_id].
2B runs at most once per request.
After pass 2, the branch clears to Mechanism 3 (zero category flags, or the hard cap).

### Sub-component 7: Assembled-path fixture set

Goal of Component
A runnable check that, on a known input, the branch, generation, collect, persist, and second inspect produce the locked before/after state (responses keyed by category_id, resolved.* unchanged by 2B, second inspect does not re-enter 2B).

Problem It Aims to Solve
Units 1–6 can pass in isolation while the loop still routes characteristic flags to 2B, drops a category_id key, or calls 2B after pass 2.


Pytest with mocks. Tests mock the provider body and stdin. Assertions check branch destination, user_responses keys, and that resolved is unchanged after 2B.

Critical Decision Choices:
Whether the fixture calls real providers or only recorded/mocked bodies: No real calls 


---

# Mechanism 4 — Persona-Driven Category Inference
Component: Lifestyle-Based Category & Characteristic Inference

## Goal of Component

Four operations, always, in this order, after Mechanism 2 has written `state.resolved`. This component does not run a skip branch: an empty result is a valid output of Operation 2, not a reason to bypass the call.

1. **Assemble inference input (always runs):** Read `persona_facts`, `payload`, and every resolved explicit category (`taxonomy_node` + `characteristics`) from the `RequirementInterpretationState`, and load the full maintained amenity-category taxonomy. These are the only inputs to the call.

2. **Persona-to-category inference (always runs):** One constrained LLM call proposes additional taxonomy categories the customer did not state. Each proposal must be a node in the maintained taxonomy, must be distinct from the explicit set under the distinctness rule below, and must be backed by persona evidence cited in `reasoning`. Generic associations are not sufficient. The call may return **zero, one, or two** categories. Zero is valid when evidence is missing or every candidate fails distinctness.

3. **Validate the body (always runs):** Accept the body only if it matches the inference schema (maximum two entries; each `taxonomy_node` constrained to the taxonomy enum) and every returned node is a real taxonomy node. The count is not clamped in code: a body with more than two entries is a validation failure, not a truncation.

4. **Strip exact-node duplicates, stamp identity, write the inferred list (always runs):** Drop every inferred entry whose `taxonomy_node` equals a resolved explicit `taxonomy_node`. Keep every remaining inferred entry. Assign `category_id` in code (the model does not emit it). Write the surviving list to a **new** `inferred_categories` field on `RequirementInterpretationState` — including an empty list when nothing survives. Do not raise for a collision. Do not modify `resolved_explicit_categories`, `persona_facts`, `payload`, `extracted`, or `user_responses`.

Priority is not tagged on either list. Explicit and inferred stay distinct because they live in different fields.

### Problem It Aims to Solve

Without this, anything outside the customer's explicit list is invisible to the specification, even when it is a predictable extension of what he already said mattered. Inference that re-labels an explicit category, or that invents a category the persona does not support, would compete with explicit priority and send the wrong scope downstream.

### Approach: Direct persona-to-category LLM inference

One call. The model receives:

- `persona_facts` (from the resolved object / extraction; same strings)
- the finalized explicit category list after Mechanism 2: each entry’s `taxonomy_node` and `characteristics`
- the `payload` (normalized customer text)
- the full maintained amenity-category taxonomy with node identifiers

The model returns `inferred_categories`: zero to two objects, each with `taxonomy_node` and `reasoning` only. `category_id` is stamped after a valid body is accepted and exact-node duplicates of the explicit set have been stripped.

The prompt states that persona facts and explicit characteristics exist so the model can judge evidence and distinctness — not so it can add a category the persona does not support, restate an explicit node, or invent a taxonomy node.

### Critical Decision Choices

### What this component reads

The full `RequirementInterpretationState` after Mechanism 2. It uses:

| Source | Fields used |
|---|---|
| `state.resolved.persona_facts` | Evidence for whether any inference is justified |
| `state.resolved.resolved_explicit_categories` | Dedup / distinctness: `taxonomy_node` and `characteristics` on each explicit entry |
| `state.payload` | Customer wording as surrounding context |
| Maintained taxonomy | Allowed nodes for every inferred `taxonomy_node` |

It does not read `user_responses`, characteristic/persona flags, or Mechanism 1 raw category names for dedup. Dedup runs against **resolved** explicit taxonomy nodes and their characteristics, not raw customer wording.

### Output object: `inferred_categories` on `RequirementInterpretationState`

This component does **not** produce a new top-level workflow object and does **not** append to `resolved_explicit_categories`. It writes one new field on the existing state.

`inferred_categories`: `list[InferredCategory]` — empty list when nothing is inferred or when every proposed node was stripped as an exact-node duplicate of the explicit set.

Each `InferredCategory`:

| Field | Type | Content |
|---|---|---|
| `taxonomy_node` | `str` | Exactly one node from the maintained amenity-category taxonomy. Not invented, renamed, or outside the list. |
| `category_id` | `int` | Stable identity stamped in code after the call, unique across explicit and inferred categories on this state. Not produced by the model. |
| `reasoning` | `str` | Which persona facts back this inference, in enough detail that a reader can see the evidence. Not a plausibility score. Not a purpose-reason for the amenity (Mechanism 3 is out of this responsibility). |

No other fields. Inferred entries do **not** carry `characteristics`, `raw_name`, `provenance`, or a priority tag.

### Cap: maximum two, minimum none

Maximum inferred categories per request: **2**, enforced **only by the schema** (`maxItems: 2`). There is no minimum. An empty list is in contract. Code does not truncate a too-long list and does not pad a too-short one.

### Distinctness (duplicate test)

An inferred category is **not distinct** (a duplicate) if the information it would add is already substantially recoverable from an explicit category or from the characteristics used to describe that explicit category. Distinct means a genuinely new discriminating dimension — not a new label for existing information.

The same tests apply among inferred items: two inferred categories must be distinct from each other as well as from the explicit set.

**Step 1 — Same taxonomy node?**

Identity, including aliases, synonyms, and trivial rewordings of the same node (singular/plural, casing, phrasing).

- If yes: duplicate. Stop. Do not run Step 2.

**Step 2 — Different node, but same information need?**

If it clears Step 1, apply all three tests. Any single “yes” is a duplicate:

1. **Reconstruction:** Could someone who only has the explicit category and its listed characteristics fully reconstruct what the inferred category is telling them? If it adds nothing beyond what is already derivable, it is redundant.
2. **Discrimination:** Does the inferred category ever split two items that the explicit category (plus its characteristics) treats identically? If it never changes how two cases are distinguished, it is not earning its place.
3. **Directionality:** Is the inferred category only a narrower subset, rephrasing, or logical consequence of an existing characteristic (rather than an independent axis)? If so, it is a repackaging.

- If any test is yes: duplicate.
- If all three are no: distinct — allow it.

**Exact-node collision with the explicit set (post-call strip, not a request failure):**

If an inferred `taxonomy_node` equals a resolved explicit `taxonomy_node`, drop that inferred entry and keep every other inferred entry that does not collide. Then write the surviving list to the state.

- One colliding node and one valid node → keep the valid node; stamp `category_id` on it; continue.
- Every inferred node collides → write `inferred_categories: []`; continue.
- Do **not** raise. Do **not** fail Mechanism 4. Do **not** fail the interpretation request.

This strip is identity-only (exact `taxonomy_node` match). Alias/synonym identity and all of Step 2 remain instruction constraints on the model; they are not a programmatic clamp and they do not fail the request.

If two inferred entries share the same `taxonomy_node`, keep the first and drop the later ones, then continue.

### How `category_id` is assigned

After the body is accepted and exact-node duplicates have been stripped, each surviving inferred entry is labeled in remaining-list order with the next integer after the maximum `category_id` already present on `state.extracted.explicit_categories`. If there are no explicit categories, numbering starts at `0`. The model never emits `category_id`.

### What the model returns vs what code writes

**Model body (schema):**

| Field | Constraint |
|---|---|
| `inferred_categories` | Array, `maxItems: 2`, empty allowed |
| `inferred_categories[].taxonomy_node` | Enum of the maintained taxonomy nodes |
| `inferred_categories[].reasoning` | Non-empty string citing persona-fact evidence |

**Code then:** checks every `taxonomy_node` is in the taxonomy set (unknown node still rejects the body); strips inferred entries whose `taxonomy_node` equals an explicit `taxonomy_node` (and later duplicates of the same inferred node); stamps `category_id` on what remains; assigns `state.inferred_categories`.

### Empty or thin persona facts

`persona_facts` may be empty. The call still runs. The instruction requires an empty `inferred_categories` list when there is not enough persona evidence for a non-generic inference, or when every candidate fails distinctness. That empty list is written to the state. There is no forced category.

### Negations

A category the persona facts negate must not be inferred.

### What this component does not do

- It does not infer or attach characteristics on inferred categories.
- It does not tag priority on inferred or explicit categories.
- It does not score plausibility. `reasoning` is the evidence record.
- It does not modify the explicit resolved set or re-run Mechanism 2.
- It does not resolve leftover characteristic or persona flags.
- It does not capture why an **explicit** category matters (Mechanism 3 is excluded).
- It does not search, retrieve, assign depth, or define metrics.


## Process Flow — Component: Lifestyle-Based Category & Characteristic Inference

Locked constraints carried into this breakdown. These are fixed at the component level and are not reopened by any sub-component below.

- Input is the `RequirementInterpretationState` after Mechanism 2 (`state.resolved` is set). The call reads `persona_facts`, each resolved explicit category's `taxonomy_node` and `characteristics`, `payload`, and the full maintained taxonomy.
- One constrained LLM call. Empty `inferred_categories` is a valid body. Maximum two inferred entries, enforced only by the schema (`maxItems: 2`). Code does not truncate a too-long list and does not pad a too-short one.
- Model body fields are `taxonomy_node` and `reasoning` only. `category_id` is stamped in code after strip. No `characteristics`, `raw_name`, `provenance`, or priority tag on inferred entries.
- Exact `taxonomy_node` match against the explicit set is stripped. Surviving entries are kept. Collision does not raise and does not fail the request. Unknown taxonomy node still rejects the whole body.
- Distinctness Step 1 aliases and all of Step 2 live in the instruction. They are not a programmatic clamp.
- `inferred_categories` is a new list on `RequirementInterpretationState`. It is not mixed into `resolved_explicit_categories`.
- This component does not capture reasons for explicit categories, does not resolve leftover flags, and does not assign depth or metrics.

Sub-components

1. Inferred Category Contract and State Field
2. Inference Instruction and Distinctness Rules
3. Constrained Inference Call and Body Validation
4. Exact-Node Strip, Identity Stamp, and State Write
5. Dummy-Provider Path Checks

Order: 1 → 2 → 3 → 4 → 5.

Sub-component 3 consumes the schema from 1 and the instruction from 2. Sub-component 4 consumes the validated body from 3. Sub-component 5 runs the assembled path end to end. Taxonomy access already exists from Mechanism 2 (`AMENITY_TAXONOMY_NODES`, `TAXONOMY_NODE_SET`). It is reused, not rebuilt.


---

### Sub-component 1: Inferred Category Contract and State Field

Goal of Component:
Define the machine-checkable types this component writes: the wire body the model returns, the `InferredCategory` entry stored on the state, and the `inferred_categories` field on `RequirementInterpretationState`.

Problem It Aims to Solve:
Mechanism 2's state has no place to hold inferred categories, and `ResolvedCategory` carries `raw_name`, `characteristics`, and `provenance`, which this component is forbidden to write. Without a separate contract, the call has nothing to constrain and later mechanisms have nothing typed to read.

Finalized Approach:
1. Split wire and store. A closed Pydantic wire model for the LLM body (`taxonomy_node`, `reasoning`, array `maxItems: 2`). A separate store type for `InferredCategory` (`taxonomy_node`, `category_id`, `reasoning`). `category_id` is absent from the provider schema, same pattern as extraction's programmatic `category_id`.

Critical Decision Choices:
* Empty `inferred_categories` default on the state is `[]`, not omitted and not `None`.
* Failure surface is new typed errors: `InferenceProviderError` and `InferenceValidationError`.
* Schema name the provider echoes with the constrained body: `inferred_categories_schema`.
* Stored entry fields remain `taxonomy_node`, `category_id`, `reasoning` only. No characteristics. No priority tag.

---

### Sub-component 2: Inference Instruction and Distinctness Rules

Goal of Component:
Build the instruction text that makes one call return zero to two taxonomy nodes, each with `reasoning` that cites persona facts, and that applies the locked distinctness tests, evidence bar, and negation rule.

Problem It Aims to Solve:
The schema caps count and enumerates nodes. It does not define when a node is allowed. Without written rules, the same persona facts can yield a restated explicit category, a generic association with no evidence, or a negated category, and nothing in the schema will reject those.

Finalized Approach:
1. Rules plus few-shot worked pairs. Written evidence rule, distinctness Step 1 and Step 2 (reconstruction, discrimination, directionality), negation rule, and negative rules (do not invent nodes, do not force a category when evidence is thin, return `[]` in that case), plus fixed worked pairs.

Critical Decision Choices:
* Few-shot cases: empty persona → `[]`; one valid distinct node; exact-node collision omitted; negation omitted; two distinct nodes; Step 2 overlap (`gym` / `fitness_center`).
* Examples use the maintained taxonomy node strings.
* The full taxonomy is rendered in the instruction, not in user content.
* `reasoning` cites which persona facts back the inference. It is not a purpose-reason for the amenity (Mechanism 3 is excluded).

---

### Sub-component 3: Constrained Inference Call and Body Validation

Goal of Component:
Execute the single inference call against the assembled user content and return either a schema-valid body or a typed failure.

Problem It Aims to Solve:
The response can exceed two entries, name a node outside the taxonomy, omit `reasoning`, or wrap extra keys. Downstream strip-and-write cannot consume that body, and an invalid body with no failure path stops the responsibility with no signal the caller can act on. Exact-node overlap with the explicit set is not this sub-component's failure. That is handled after a valid body exists.

Finalized Approach:
1. Provider-constrained structured output, then an independent second check. Pass the schema (including the taxonomy enum on `taxonomy_node` and `maxItems: 2`) at generation time. Validate the returned object with the same model. Then check every `taxonomy_node` is in `TAXONOMY_NODE_SET`. Unknown node rejects the whole body. More than two entries is a schema failure, not a truncation.

Critical Decision Choices:
* Reuse the existing ordered provider chain (`self._providers`, OpenAI then Groq).
* User content is a JSON dump of the locked inputs: persona facts, explicit `taxonomy_node` plus `characteristics`, and payload. The full taxonomy is already in the instruction.
* Invalid body (schema miss or unknown node) rejects the whole response. Count is not clamped in code.
* The call always runs, including when `persona_facts` is empty. `[]` is a valid body.
* One call for all candidates. Exact-node collision with the explicit set is not a validation failure here.

---

### Sub-component 4: Exact-Node Strip, Identity Stamp, and State Write

Goal of Component:
From a valid inference body, drop exact-node duplicates, stamp `category_id` on what remains, write `state.inferred_categories`, and sequence `interpret()` so this component runs after Mechanism 2.

Problem It Aims to Solve:
A schema-valid body can still repeat an explicit `taxonomy_node` or repeat the same inferred node twice. Failing the request on that collision would discard a valid sibling entry. Leaving the collision in place would put an inferred category on the same node as an explicit one and break explicit priority. Without a write onto the existing state, later mechanisms have no inferred list. Without an `interpret()` call after Mechanism 2, this component never runs.

Finalized Approach:
1. In-place filter and mutate. Walk the validated list. Drop an entry whose `taxonomy_node` is already in the explicit set. Drop a later inferred entry that repeats an earlier inferred `taxonomy_node`. Stamp `category_id` on survivors. Assign `state.inferred_categories`. `interpret()` calls this after `run_explicit_category_resolution`.

Critical Decision Choices:
* `category_id` is `max(extracted.explicit_categories.category_id) + 1`, or `0` if there are no explicit categories. It is not taken from `resolved_explicit_categories` only.
* Stripped collisions are logged with the node and reason `exact_explicit_duplicate` or `duplicate_inferred_node`. Logging does not change the stored result beyond the strip.
* Collision with an explicit node never raises. Survivors (zero, one, or two) are written. Empty list after a full strip is success.
* Do not mix inferred entries into `resolved_explicit_categories`. Do not stamp ids until after the strip.

---

### Sub-component 5: Dummy-Provider Path Checks

Goal of Component:
Run a fixed set of inference bodies through the assembled path with a dummy provider (no live API call) and produce a pass or fail per check.

Problem It Aims to Solve:
Distinctness in the instruction is not checkable from the schema. Exact-node strip, empty-list success, id stamping, and "collision does not fail the request" are only visible if a known body is pushed through Operations 3 and 4. A live model call would change the body between runs and would not prove those rules.

Finalized Approach:
1. Dummy provider. A test double returns a fixture JSON body. The real validate, strip, stamp, and write path runs against it. Assertions check the stored `inferred_categories` and that no exception is raised on exact-node collision.

Critical Decision Choices:
* Fixture set: empty persona → `[]`; one valid node; two valid nodes; one collision plus one sibling (keep sibling, do not raise); both collide → `[]` (do not raise); two inferred entries with the same node (keep first); unknown taxonomy node (reject body); more than two entries (reject body, do not truncate).
* Instruction-only rules (Step 2 overlap, negation, thin-evidence `[]`) are asserted via dummy bodies that already obey them.
* No live provider call in these checks.
* Maximum two is a schema failure, not truncation. Exact-node strip is not a request failure.


---

# Mechanism 5 — Depth Assignment
## Component: Per-Category Depth Calibration

### Goal of Component

Four operations, in this order, after Mechanism 4 has written `state.inferred_categories`. Mechanism 3 is excluded from the feature and is not a prerequisite. This component assigns one depth to every remaining category — explicit and inferred — from one shared three-level scale. Floors and escalation targets differ by origin; the control surface (start at the origin's floor, escalate only on a trigger) is the same for every category.

**Branch — both lists empty:** If `state.resolved.resolved_explicit_categories` and `state.inferred_categories` are both empty, skip Operations 1–4. Leave both lists unchanged. Do not call the model. Do not fail the request.

**Branch — at least one category exists:** Run all four operations.

1. **Assemble depth-assignment input (runs when at least one category exists):** Read, from the `RequirementInterpretationState`, the `payload`, `persona_facts`, every resolved explicit category (`category_id`, `taxonomy_node`, `characteristics`), and every inferred category (`category_id`, `taxonomy_node`, `reasoning`). Label each submitted category as `explicit` or `inferred` so the model can apply the matching floor. Load the pre-defined three-level scale, the origin floors, the escalation rule, the acceptance test, and the metric contract into the instruction. These are the only inputs to the call.

2. **Constrained depth assignment (runs when at least one category exists):** One batched LLM call assigns a depth to every submitted category in a single pass. The model starts each category at its origin floor and escalates only when a trigger exists (see Floor assignment and How the agent moves between levels). It returns one `depth` per `category_id`. It does not invent categories, drop categories, emit metric lists, or call retrieval tools.

3. **Validate the body (runs when the call ran):** Accept the body only if it matches the depth-assignment schema, every `depth` is in `{basic_profile, operating_details, specific_attributes}`, no **explicit** `category_id` is assigned `basic_profile`, and the set of `category_id` values is exactly the set that was submitted — no missing, extra, or duplicate ids. A mismatch rejects the whole body. Code does not fill a missing id with a floor, does not drop extras, and does not clamp an illegal value up or down.

4. **Stamp depth onto each category (runs when the body is accepted):** For each assignment, write `depth` onto the matching `ResolvedCategory` or `InferredCategory` by `category_id`. Do not modify `taxonomy_node`, `characteristics`, `reasoning`, `raw_name`, `provenance`, `persona_facts`, `payload`, `extracted`, or `user_responses`. Do not mix inferred entries into `resolved_explicit_categories`.

### Problem It Aims to Solve

A fixed shallow or fixed deep pass either omits what the customer needs or drowns them in unwanted detail. Without one consistent rule, two categories the customer emphasized equally can receive arbitrarily different rigor, an inferred category can consume the same fetch budget as an explicit one with no trigger, and later metric/retrieval stages have no shared signal for how much to fetch — or they fetch attributes that cannot actually be resolved.

### Approach: Scale-in-prompt, origin-gated floors, one batched LLM assignment

The depth scale is pre-defined in the instruction so the model knows what each level means (question, contents, tools, whether metrics are contract-gated). Assignment is not a per-`taxonomy_node` lookup table. One constrained call starts each category at its origin floor and moves up only on an explicit trigger.

The assigned depth is the information band later stages (Mechanism 6 and retrieval) may fetch for that category. This component does not enumerate, accept, or reject individual metrics. The metric contract below is part of the scale definition and is the gate Mechanism 6 / retrieval must apply to every dynamically chosen metric at `operating_details` and `specific_attributes`.

### Critical Decision Choices

#### Depth scale

Three levels exist. All three are defined in the prompt. All three are assignable, subject to the origin floors below.

| Level | Question it answers | Contents | Tools | Contract-gated? |
|---|---|---|---|---|
| `basic_profile` | Is it here, and can I reach it — at what cost? | Identity (name, category, address, `place_id`, coords) + accessibility metrics: travel distance and duration per mode (walk / drive / cycle), `transit_details` (Routes API, travelMode TRANSIT; bus, subway, and train allowed in the same call). | Google Maps: Places (identity and walk/drive/cycle `routingSummaries`) + Routes API (`transit_details`). Fully Maps-resolvable. | No — these are fixed, known-resolvable dimensions. |
| `operating_details` | Is it any good, and how does it run? | `basic_profile` + operational dimensions (hours, contact/website, rating, review volume, price level) + an LLM-defined, per-category quality set. The quality set is category-appropriate (restaurant vs gym vs school differ). Each proposed quality metric must pass the metric contract. | Maps (hours, rating, ratings count, `price_level`, attributes) + parallel web search (reputation synthesis). | Yes — every LLM-proposed quality metric goes through the contract. The fixed Maps operational dimensions do not. |
| `specific_attributes` | Does it fit my particular situation? | User-specific metrics beyond the above — attributes the user emphasized, or that persona / inferred reasoning shows they would need. | Parallel web search + firecrawl/diffbot on targeted pages (official site, schedule, menu, pricing). | Yes — every metric goes through the contract. |

Assigned `depth` type: `Literal["basic_profile", "operating_details", "specific_attributes"]`.

Higher levels include the contents of every level below them. Choosing `operating_details` includes `basic_profile`. Choosing `specific_attributes` includes both lower bands.

The tools named in this table are **not** called here. They describe what the assigned band authorizes later stages to use.

#### Floor assignment

| Category origin | Floor | Escalation |
|---|---|---|
| Explicit | `operating_details` — always. Explicit categories never receive `basic_profile`. | Escalate to `specific_attributes` when the user named a specific attribute for that category, or a persona / situation criterion in the input implies a judging question that `operating_details` cannot answer. |
| Inferred | `basic_profile` — always, by default. | Stay at `basic_profile` unless there is a signal in the input pointing to a specific attribute of **that** inferred category. When such a signal exists, inspect the nature of the attribute: assign `operating_details` if it is operational / quality-level; assign `specific_attributes` if it is a narrow, user-specific characteristic. |

Nothing drops below its own floor. No trigger → stay at the floor.

#### How the agent moves between levels

1. Start at the origin floor. Explicit → `operating_details`. Inferred → `basic_profile`.
2. Escalate on an explicit trigger only — a named attribute or a persona / inferred criterion the current level cannot answer (see Acceptance test). For inferred categories, the same trigger also chooses which higher level (`operating_details` vs `specific_attributes`) from the attribute's nature. No trigger → stay at the floor. That is what prevents both over-fetching and under-fetching.
3. The metric contract caps every later fetch at the two dynamic levels: Mechanism 6 may propose freely, but only contract-passing metrics resolve, so expensive tools (firecrawl/diffbot) fire only on things known to be retrievable. This component does not run that gate.

#### Acceptance test (applied identically to every level)

After this level's metrics would be filled, can the user decide whether to weight this amenity as a decision factor? If the fills would still leave them at "I know it exists but I cannot tell whether it matters," the level under-delivers for that criterion.

That is the pass/fail bar for "the current level cannot answer," not a feeling. In this component there is no fetch yet, so the test is prospective: given the trigger, would the current floor's band let the user make that decision? If no, and a trigger exists, escalate. If no trigger exists, stay at the floor even if the band is thin — inferred categories with no attribute-level signal remain `basic_profile`.

#### Metric contract (gates `operating_details` quality metrics and every `specific_attributes` metric)

Every dynamically chosen metric — an `operating_details` quality metric or a `specific_attributes` metric — must fill all six fields. If it cannot fill even one, the metric is rejected and never fetched. `basic_profile` dimensions are not run through this contract; they are fixed and Maps-resolvable.

This component does not emit metrics. The contract is inlined in the depth instruction so the assignment model knows what the two dynamic levels contain, and it is the gate Mechanism 6 / retrieval must apply.

| Field | Content |
|---|---|
| `label` | Human-readable metric name. |
| `question` | The exact decision question it answers **for this user** — tied, directly or indirectly, to their instruction or a persona fact. Direct = they asked for it. Indirect = a persona / inferred fact implies they would weigh it. Forces relevance. |
| `value_type` | One of: `number+unit` \| `boolean` \| `enum[fixed set]` \| `date/time`. Free-form prose as a **final** value is disallowed — the value must be comparable / interpretable. |
| `resolution_source` | Concrete tool + target: which Maps field, or the shape of the web-search query, or which page type firecrawl/diffbot hits. |
| `verification` | What evidence confirms the value (e.g. "stated on official site", "≥3 independent reviews corroborate", "listed in Maps attributes"). |
| `null_policy` | What to emit if unresolved — must be `null` / `"unknown"`, never guessed. |

**Rejection rule (why "cozy" fails):** `is it cozy?` → `value_type` has no enumerable range, `resolution_source` names nothing concrete, `verification` cannot be specified → rejected.

**Reformulated to pass:** `label: ambiance`; `question: "user wants a quiet place to work (persona: remote worker) — is it quiet or lively?"` (indirect relevance); `value_type: enum[quiet, mixed, lively]`; `resolution_source: web search + review-term frequency`; `verification: dominant sentiment across ≥5 reviews mentioning noise/atmosphere`; `null_policy: "unknown"` → accepted.

#### How depth is assigned

Dynamically, by the LLM, in one batched call. Not from a pre-built per-category-type table. Every category in the batch sees the same scale, the same floors, the same trigger rule, and the same acceptance test, so two categories with the same origin and equivalent triggers are not given different rigor for no reason traceable to the input.

The instruction must mark each submitted row as `explicit` or `inferred`. The model does not infer origin from the node name.

#### Stated-detail signals (what counts as a trigger)

| Signal | Used for | Content |
|---|---|---|
| `payload` | Every category | Normalized customer text. A named attribute, or a situation criterion, that points at this category. |
| `characteristics` | Explicit categories only | Qualities already stored on the `ResolvedCategory`. Empty list means no named attribute from extraction. |
| `reasoning` | Inferred categories only | Persona-fact evidence already stored on **that** `InferredCategory`. This is the stand-in for characteristics, which inferred entries do not carry. A trigger for an inferred category must point at that inferred node, not at a different explicit one. |
| `persona_facts` | Every category | Situation and lifestyle facts. A criterion implied here can trigger escalation when the current floor cannot answer it. |

Leftover `characteristic` and `persona` flags on `state.resolved.ambiguity_flags` are **not** inputs. `user_responses` are **not** inputs.

A **trigger** is a named attribute or a persona / inferred criterion, found in those signals, that the current floor cannot answer under the acceptance test. Volume of wording alone is not a trigger. Centrality of a lifestyle topic is not a trigger unless it implies a judging criterion the floor cannot answer.

#### Inferred categories

Inferred categories do **not** share the explicit floor. Their floor is `basic_profile`. They are not forced to stay there: a signal in `payload`, `persona_facts`, or that entry's `reasoning` that points at a specific attribute of that inferred category promotes them. The LLM then assigns `operating_details` or `specific_attributes` from the attribute's nature (operational / quality vs narrow user-specific). No such signal → `basic_profile`.

#### Write target

This component does **not** produce a new top-level workflow object. It stamps `depth` onto each existing category entry.

`ResolvedCategory` after this component:

| Field | Type | Content |
|---|---|---|
| `category_id` | `int` | Unchanged. Identity from Mechanism 2. |
| `taxonomy_node` | `str` | Unchanged. |
| `raw_name` | `str` | Unchanged. |
| `characteristics` | `list[str]` | Unchanged. |
| `provenance` | `Provenance` | Unchanged. |
| `depth` | `Literal["basic_profile", "operating_details", "specific_attributes"]` | Written here. Required on every remaining explicit entry after a successful stamp. Same three-member enum as inferred. Never `basic_profile` in practice: validation rejects that assignment before stamp. |

`InferredCategory` after this component:

| Field | Type | Content |
|---|---|---|
| `taxonomy_node` | `str` | Unchanged. |
| `category_id` | `int` | Unchanged. Identity from Mechanism 4. |
| `reasoning` | `str` | Unchanged. |
| `depth` | `Literal["basic_profile", "operating_details", "specific_attributes"]` | Written here. Required on every remaining inferred entry after a successful stamp. Floor is `basic_profile`. |

Before this component runs, `depth` is unset (`None`) on both types. After a successful return with at least one category, no remaining entry has `None`.

#### What this component reads

The full `RequirementInterpretationState` after Mechanism 4. It uses:

| Source | Fields used |
|---|---|
| `state.payload` | Normalized customer wording (`normalized_text`) as trigger context |
| `state.resolved.persona_facts` | Situation / lifestyle criteria that can trigger escalation |
| `state.resolved.resolved_explicit_categories` | `category_id`, `taxonomy_node`, `characteristics`; origin = explicit |
| `state.inferred_categories` | `category_id`, `taxonomy_node`, `reasoning`; origin = inferred |
| Depth-scale text | Three-level definition, floors, escalation rule, acceptance test, and metric contract, inlined in the instruction |

It does not read `user_responses`, leftover ambiguity flags, `extracted.explicit_categories` names for assignment, or any Mechanism 3 reason/priority field (Mechanism 3 is excluded).

#### What the model returns vs what code writes

**Model body (schema):**

| Field | Constraint |
|---|---|
| `assignments` | Array. Length must equal the number of submitted categories. Empty only when the call was skipped (both lists empty). |
| `assignments[].category_id` | Integer. Must echo a submitted id. |
| `assignments[].depth` | Enum: `basic_profile` \| `operating_details` \| `specific_attributes` |

**Code then:** checks the id set is exactly the submitted set; rejects the body if any **explicit** id is assigned `basic_profile`; stamps `depth` onto the matching `ResolvedCategory` or `InferredCategory`; leaves every other field unchanged.

Reuses `self._providers` and `_call_providers` with a new schema name. Total provider failure raises a typed provider error with `stage`. A schema-invalid, id-mismatched, or explicit-below-floor body raises a typed validation error with `stage`. Validation is all-or-nothing.

#### Empty or thin signals

`persona_facts` may be empty. `characteristics` may be empty. `reasoning` is non-empty on every inferred entry that exists, but may be thin. The call still runs whenever at least one category exists. Thin or empty signals are **not** a skip and **not** a failure: explicit stays at `operating_details`; inferred stays at `basic_profile`.

#### What this component does not do

- It does not emit, accept, or reject individual metrics. Mechanism 6 applies the metric contract.
- It does not search, retrieve, or score an amenity, and it does not call Maps, parallel web search, firecrawl, or diffbot.
- It does not tag priority or capture why an explicit category matters (Mechanism 3 is excluded).
- It does not resolve leftover characteristic or persona flags.
- It does not add, drop, or remap categories.
- It does not mix inferred entries into `resolved_explicit_categories`.
- It does not assign `basic_profile` to an explicit category.

#### Part 3 — Before/After state and residual gaps

**Branch A — at least one category (call runs)**

**Before Mechanism 5** (state after Mechanism 4):
- `state.resolved.resolved_explicit_categories`: each entry has `category_id`, `taxonomy_node`, `raw_name`, `characteristics`, `provenance`; `depth` is `None`
- `state.inferred_categories`: zero to two entries, each with `taxonomy_node`, `category_id`, `reasoning`; `depth` is `None`
- `state.payload`, `persona_facts`, `extracted`, `user_responses`, `category_resolution_passes`: unchanged from Mechanism 4

**After Mechanism 5:**
- Every remaining `ResolvedCategory` has `depth` in `{operating_details, specific_attributes}`
- Every remaining `InferredCategory` has `depth` in `{basic_profile, operating_details, specific_attributes}`
- All other fields on those objects, and every other state field, unchanged

**Branch B — zero categories (call skipped)**

**Before:** both category lists empty; `depth` has nothing to stamp.

**After:** both lists still empty. No model call. No failure.

| State field | Before M5 | After M5 (Branch A) | After M5 (Branch B) |
|---|---|---|---|
| `resolved.resolved_explicit_categories` | M2/M4 entries, `depth=None` | same entries, `depth` stamped (`operating_details` or `specific_attributes`) | `[]` unchanged |
| `inferred_categories` | M4 list (0–2), `depth=None` | same entries, `depth` stamped (`basic_profile`, `operating_details`, or `specific_attributes`) | `[]` unchanged |
| `resolved.persona_facts` / `payload` | carried | unchanged | unchanged |
| `extracted` / `user_responses` | carried | unchanged | unchanged |
| `resolved.ambiguity_flags` | leftover characteristic/persona flags, if any | unchanged | unchanged |
| `category_resolution_passes` | from Mechanism 2 | unchanged | unchanged |

**(a) Assumptions baked from D1–D7, this feedback, and un-overridden safe defaults**

- All three levels are assignable. Origin floors override the earlier "never assign `basic_profile`" / "same floor for inferred" answers.
- Both store types use the full three-member `depth` enum. Wire schema allows all three. Code rejects explicit `basic_profile` before stamp.
- One batched call; model echoes `category_id`; origin is labeled in the prompt, not inferred.
- `interpret()` sequences this component immediately after Mechanism 4. Mechanism 3 is not inserted.
- Leftover flags are ignored. No rationale field and no metric objects are stored on the category.
- Zero-category skip does not fail. No trigger → origin floor. Code does not overwrite a valid escalation.
- Tools and the metric contract describe later-stage work. This component does not fetch.

**(b) Gaps vs current contracts**

- `ResolvedCategory` and `InferredCategory` have no `depth` field yet.
- `interpret()` currently returns after Mechanism 4; it does not call this component.
- No depth-assignment schema, instruction module, or typed errors exist yet. Those are implementation work, not missing upstream inputs.
- Upstream inputs this component needs (`payload`, `persona_facts`, explicit `characteristics`, inferred `reasoning`, `category_id` on both lists) already exist on the post-M4 state. There is no missing upstream field once `depth` is added to the two dataclasses.
- Mechanism 6's spec does not yet name this six-field metric contract. The contract is locked here as level semantics; Mechanism 6 must apply it when it proposes metrics, or the two specs will disagree.


## Process Flow — Component: Per-Category Depth Calibration

Locked constraints carried into this breakdown. These are fixed at the component level and are not reopened by any sub-component below.

- Input is the `RequirementInterpretationState` after Mechanism 4 (`state.resolved` is set, `inferred_categories` is written). Mechanism 3 is excluded and is not a prerequisite.
- One constrained LLM call when at least one category exists. If both category lists are empty, skip the call, leave both lists unchanged, and do not fail the request.
- Three-level scale (`basic_profile`, `operating_details`, `specific_attributes`) is pre-defined in the instruction. Assignment is not a per-`taxonomy_node` lookup table.
- Explicit floor is `operating_details`. Inferred floor is `basic_profile`. Escalate only on a trigger. No trigger means stay at the floor.
- Wire schema allows all three depth values. Code rejects the whole body if an explicit `category_id` is assigned `basic_profile`. Code does not fill, drop, or clamp.
- Model body fields are `category_id` and `depth` only. This component does not emit metrics. The metric contract is instruction text for later stages.
- `depth` is stamped onto each existing `ResolvedCategory` and `InferredCategory`. Inferred entries stay in `inferred_categories`.
- Reuse `self._providers` and `_call_providers`. Typed provider error vs typed validation error, each with `stage`. Validation is all-or-nothing.
- This component does not search, retrieve, call Maps / web search / firecrawl / diffbot, resolve leftover flags, or tag priority.

Sub-components

1. Depth Contract and State Field
2. Depth Assignment Instruction
3. Constrained Depth Call and Body Validation
4. Depth Stamp, Empty Skip, and interpret Sequencing
5. Dummy-Provider Path Checks

Order: 1 → 2 → 3 → 4 → 5.

Sub-component 3 consumes the schema from 1 and the instruction from 2. Sub-component 4 consumes the validated body from 3 (or takes the empty-list skip). Sub-component 5 runs the assembled path end to end. The provider chain already exists from Mechanism 1. It is reused, not rebuilt.


---

### Sub-component 1: Depth Contract and State Field

Goal of Component:
Define the machine-checkable types this component writes: the wire body the model returns, the `depth` field on `ResolvedCategory` and `InferredCategory`, and the typed errors the call can raise.

Problem It Aims to Solve:
Neither store type has a `depth` field. The call has nothing to constrain against and nothing to validate against. Later mechanisms have no typed band to read. Mixing `depth` into `ResolvedCategory` without a separate wire shape would also force the model to emit `raw_name`, `characteristics`, and `reasoning`.

Finalized Approach:
1. Split wire and store. Closed Pydantic wire model for the LLM body (`assignments[]` of `category_id` + `depth`). Dataclass field `depth` on the existing store types. `depth` is `None` until stamped. Same split as `InferredCategoriesResult` / `InferredCategory`.

Critical Decision Choices:
* Stored `depth` type on both `ResolvedCategory` and `InferredCategory` is the full three-member enum: `basic_profile | operating_details | specific_attributes`. Explicit `basic_profile` is still rejected at validation, before stamp.
* Failure surface is new typed errors: `DepthAssignmentProviderError` and `DepthAssignmentValidationError`.
* Schema name the provider echoes with the constrained body: `depth_assignment_schema`.
* No metric objects, rationale field, or new top-level state list.

---

### Sub-component 2: Depth Assignment Instruction

Goal of Component:
Build the instruction text that makes one call assign a depth to every submitted category using the locked scale, origin floors, trigger-only escalation, acceptance test, and inlined metric contract.

Problem It Aims to Solve:
The schema enumerates depth values and requires `category_id`. It does not define floors, what a trigger is, or what each level contains. Without written rules, an explicit category can be assigned `basic_profile`, an inferred category with no attribute signal can be raised to `specific_attributes`, or two categories with the same origin and equivalent evidence can receive different depths.

Finalized Approach:
1. Rules plus few-shot worked pairs, in a dedicated instruction module with a `build_*` function (same pattern as `inference_instruction.py`). Task statement, scale, floors, escalation, acceptance test, metric contract, negative rules, and fixed worked pairs live as module-level strings.

Critical Decision Choices:
* Few-shot cases: explicit stay at `operating_details`; explicit escalate to `specific_attributes`; inferred stay at `basic_profile`; inferred escalate to `operating_details`; inferred escalate to `specific_attributes`; negative pair (explicit `basic_profile` is wrong).
* Origin label (`explicit` / `inferred`) lives in user content. The model does not infer origin from `taxonomy_node`.
* Metric contract (six fields plus the cozy / `ambiance` pair) is inlined in the instruction. This component still does not emit metrics.
* Worked inputs must not be reused as the live sample-runner seed.

---

### Sub-component 3: Constrained Depth Call and Body Validation

Goal of Component:
When at least one category exists, execute the single depth-assignment call and return either a schema-valid body whose `category_id` set matches the submitted set and whose explicit rows are not `basic_profile`, or a typed failure.

Problem It Aims to Solve:
The response can omit an id, invent an id, duplicate an id, assign `basic_profile` to an explicit category, or wrap extra keys. Downstream stamp cannot consume that body. Repairing it (fill, drop, clamp) would write a depth the model did not assign. An invalid body with no failure path stops the responsibility with no signal the caller can act on.

Finalized Approach:
1. Provider-constrained structured output, then an independent second check. Pass the schema (three-value `depth` enum) at generation time. Validate the returned object with the same model. Then require the `category_id` set equals the submitted set, and reject the body if any explicit id is assigned `basic_profile`. First failure raises `DepthAssignmentValidationError`. Code does not fill, drop, or clamp.

Critical Decision Choices:
* Reuse the existing ordered provider chain (`self._providers`, OpenAI then Groq).
* User content is a JSON dump of origin-labeled rows, `payload`, and `persona_facts`.
* Coverage (id set) and explicit-floor failures are validation errors, not provider errors.
* Fallback to the next provider is only for `LLMProviderError`, not for a returned invalid body.
* The call always runs when at least one category exists, including thin `persona_facts` or empty `characteristics`. Empty both lists is not this sub-component (skip is sub-component 4).

---

### Sub-component 4: Depth Stamp, Empty Skip, and interpret Sequencing

Goal of Component:
From a valid body, write `depth` onto each matching store entry by `category_id`. If both category lists are empty, skip Operations 1 through 4 without a model call and without failure. Sequence `interpret()` so this component runs immediately after Mechanism 4.

Problem It Aims to Solve:
A valid body that is not written leaves every `depth` as `None`. Mechanism 6 then has no band. Filling missing ids here would hide a validation miss. Without an empty-list skip, a request with no categories would still call the model. Without an `interpret()` call after Mechanism 4, this component never runs.

Finalized Approach:
1. In-place stamp. Build a `category_id` lookup over both lists. For each assignment, set `.depth` on the matching object. If both lists are empty, return the state unchanged before instruction or call. `interpret()` calls this immediately after `run_persona_driven_category_inference`. Mechanism 3 is not inserted.

Critical Decision Choices:
* Lookup is by `category_id`, not by `taxonomy_node` name.
* Log a stamp event with counts per depth value.
* Empty skip is success, not a validation error.
* Do not modify `taxonomy_node`, `characteristics`, `reasoning`, `raw_name`, `provenance`, `persona_facts`, `payload`, `extracted`, or `user_responses`. Do not mix inferred entries into `resolved_explicit_categories`.

---

### Sub-component 5: Dummy-Provider Path Checks

Goal of Component:
Run a fixed set of depth-assignment bodies through the assembled path with a dummy provider (no live API call) and produce a pass or fail per check.

Problem It Aims to Solve:
Floors, trigger rules, and the metric contract in the instruction are not checkable from the schema. Id-set equality, explicit `basic_profile` rejection, empty-list skip, and "code does not clamp" are only visible if a known body is pushed through sub-components 3 and 4. A live model call would change the body between runs and would not prove those rules.

Finalized Approach:
1. Dummy provider returns fixture JSON. The real validate and stamp path runs against it. Assertions check stamped `depth`, that other fields are unchanged, and that illegal bodies raise.

Critical Decision Choices:
* Fixture set: empty both lists (no call, no error); explicit `basic_profile` (reject, no stamp); missing id (reject); extra id (reject); duplicate id (reject); valid mixed batch (explicit `operating_details` / `specific_attributes`, inferred `basic_profile` / higher); other fields unchanged.
* Instruction-only rules (trigger vs no-trigger) are asserted via dummy bodies that already obey them. They are not a programmatic clamp.
* No live provider call in these checks. A live sample runner is a later implementation-plan artifact, not this sub-component.


---

# Mechanism 6 — Category-Specific Metric & Fact Definition

## Component: Per-Category Metric Definition

### Goal of Component

Six operations, in this order, after Mechanism 5 has stamped `depth` onto every category. Mechanism 3 is excluded and is not a prerequisite. This component defines, for every category that needs more than the fixed profile, the dynamic metrics its assigned depth authorizes, and records them in a separate workflow object. Every metric must pass the metric contract defined in Mechanism 5. Metrics that fail a code-side contract check are dropped; nothing is repaired.

**Eligible category:** a `ResolvedCategory` or `InferredCategory` whose `depth` is `operating_details` or `specific_attributes`. A `basic_profile` category is not eligible: its content is the fixed dimensions only.

**Branch A — no eligible category** (both lists empty, or every category is `basic_profile`): skip Operations 1–5 and do not call the model. Run Operation 6 only: write one `CategoryMetricSet` per existing category with `metrics = None` (nothing to write when both lists are empty). Do not fail the request.

**Branch B — at least one eligible category:** run all six operations.

1. **Assemble metric-definition input (runs in Branch B):** Read, from the `RequirementInterpretationState`, `payload.normalized_text`, `resolved.persona_facts`, the leftover characteristic and persona flags on `resolved.ambiguity_flags` (context only), and every eligible category: `category_id`, `taxonomy_node`, origin (`explicit` or `inferred`), `depth`, and `characteristics` (explicit) or `reasoning` (inferred). Label each row with origin and assigned depth in the user content. Load the depth scale, the band rule, the metric contract, the fixed-dimension list (as "do not propose these"), the negative rules, and the worked examples into the instruction.

2. **Constrained metric definition (runs in Branch B):** One batched LLM call returns, for every submitted `category_id`, a list of metrics. Each metric carries the six contract fields plus a `band`. The model does not re-assign depth, does not define fixed dimensions, does not fetch anything, and does not add, drop, or remap categories.

3. **Validate the body against the schema and the id set (runs after the call):** Accept the body only if it matches the metric-definition schema — every metric has every field, with the right types and values from the closed sets — and the set of returned `category_id` values is exactly the submitted set: no missing, extra, or duplicate ids. Either miss rejects the whole body with a typed validation error. Code does not fill, drop, or reorder ids.

4. **Apply the metric contract rules per metric (runs on an accepted body):** Check each metric against the contract rules K1–K6 — the rules a schema cannot express. A metric that fails any rule is dropped and logged with its failed rule. Metrics that pass are kept in the order the model returned them.

5. **Report shortfalls (runs after Operation 4):** For each eligible category, note whether it has zero surviving `operating_details`-band metrics, or (when `depth = specific_attributes`) zero surviving `specific_attributes`-band metrics. This is a logged report, not a failure and not a repair.

6. **Write metric sets to state (runs after Operation 5, or alone in Branch A):** Append one `CategoryMetricSet` to `state.category_metrics` for every category (explicit entries first, then inferred), matched by `category_id`. `taxonomy_node` is copied from the matching `ResolvedCategory` or `InferredCategory`. `metrics` is the surviving list for an eligible category (possibly empty) and `None` for a `basic_profile` category. Do not modify `ResolvedCategory`, `InferredCategory`, or any other state field.

### Problem It Aims to Solve

Without one shared rule for what a metric must contain, "obviously relevant" information is reasoned out fresh each run: one run proposes `is it cozy?`, another proposes a comparable, resolvable metric, and retrieval either burns expensive tools on unresolvable questions or returns prose the customer cannot compare. Without a band rule, a category assigned `operating_details` could receive `specific_attributes`-level metrics, defeating Mechanism 5's depth decision. Without a stated owner for the contract, Mechanism 5 assumes Mechanism 6 applies it and Mechanism 6 assumes nothing. Consistency here means every category is treated by the same contract and the same depth-scale approach, not that every category of the same type receives an identical stored template.

### Approach: Depth-band-driven definition, one batched call, contract-gated, drop-only rejection

The depth scale from Mechanism 5 tells the model what each band contains and which tools it may use. The model defines only the two dynamic bands: an `operating_details` quality set and a `specific_attributes` user-specific set. The fixed dimensions are known to code and are never defined by the model. One constrained call sees every eligible category together so the same scale, contract, and rules apply to all of them. No predefined metric list per category type or taxonomy group exists in code or is required in the prompt. The prompt carries a few worked examples only. Results live in their own state object, keyed by `category_id`.

### Critical Decision Choices

#### What "baseline" means in this component

The always-captured baseline is the **fixed dimensions** for the assigned depth. It is a code-owned constant, not a model output, and it is not stored on the state. Everything else is dynamic, defined by the model in this call, and gated by the contract.

#### Fixed dimensions by depth

| Depth | Fixed dimensions implied (cumulative) | Owner |
|---|---|---|
| `basic_profile` | Identity: name, category, address, website, `place_id`, coords. Accessibility: travel distance and duration per mode (walk / drive / cycle), `transit_details` (Routes API, travelMode TRANSIT; bus, subway, and train allowed in the same call). | Code constant. |
| `operating_details` | `basic_profile` + hours, contact (phone), rating, review volume, price level. | Code constant. |
| `specific_attributes` | `operating_details` fixed dimensions. No additional fixed dimensions. | Code constant. |

Later stages read this constant by `depth`. It is the single source of truth for the fixed part of what is fetched.

#### Bands the model may define

A **band** is the depth level a metric belongs to: `operating_details` or `specific_attributes`. Bands are cumulative: a `specific_attributes` category carries the quality set and the user-specific set, and each metric is tagged with the band it came from.

| Assigned depth | Bands the model may emit | Minimum expected | Maximum |
|---|---|---|---|
| `basic_profile` | none (category is not submitted) | — | — |
| `operating_details` | `operating_details` | ≥1 (reported, not enforced) | 4 |
| `specific_attributes` | `operating_details` and `specific_attributes` | ≥1 of each (reported, not enforced) | 4 per band |

The band tag lets code check that no metric sits above its category's depth, and that each band uses only its allowed tools. The cap keeps each category's list short and later fetch cost bounded.

#### How metrics are defined per band

| Band | Question it answers | Tie to the user (goes in `question`) | Allowed tools |
|---|---|---|---|
| `operating_details` | Is it any good, and how does it run — beyond the fixed dimensions? | The category itself is a valid tie: the customer explicitly asked for it (explicit), or that entry's `reasoning` supports it (inferred). The `question` states which. | `google_maps` (attributes not already fixed), `parallel_web_search` |
| `specific_attributes` | Does it fit my particular situation? | Must point at the trigger that raised the depth: a named characteristic, a payload statement, a persona fact, or the inferred entry's `reasoning`. | `parallel_web_search`, `firecrawl` |

Decision test, applied to every metric: once resolved, would this value change how the customer weights or ranks this category? If not, the metric is not proposed. A metric must not restate a fixed dimension.

#### Metric contract as typed fields

The six fields come from Mechanism 5. This component types them and adds `band`:

| Field | Wire type | Content |
|---|---|---|
| `label` | `str` | Human-readable metric name. |
| `question` | `str` | The exact decision question for this user, tied directly or indirectly to their instruction, a persona fact, or the category's own request/inference. |
| `value_type` | `Literal["number_with_unit", "boolean", "enum", "date_time"]` | Maps to `number+unit`, `boolean`, `enum[fixed set]`, `date/time`. Free-form prose is not a value type. |
| `unit` | `str \| None` | Required when `value_type = number_with_unit`; `None` otherwise. |
| `enum_values` | `list[str]` | ≥2 distinct members when `value_type = enum`; empty otherwise. |
| `resolution_source` | `{tool: Literal["google_maps", "parallel_web_search", "firecrawl"], target: str}` | Concrete tool and target: the Maps field, the shape of the search query, or the page type firecrawl fetches. |
| `verification` | `str` | What evidence confirms the value. |
| `null_policy` | `Literal["null", "unknown"]` | What to emit if unresolved. Never a guess. |
| `band` | `Literal["operating_details", "specific_attributes"]` | The band the metric belongs to. |

#### Three-layer validation

| Layer | What it checks | Action on failure |
|---|---|---|
| 1. Schema (Operation 3) | Field structure of every metric: all keys present, no extra keys, correct types, values inside the closed sets (`value_type`, `null_policy`, `tool`, `band`). The schema is passed at generation time and the returned body is validated against the same model. This is what keeps metric structure consistent across categories and runs. | Reject the whole body. Typed validation error with `stage`. |
| 2. Id set (Operation 3) | Returned `category_id` set equals the submitted set. | Reject the whole body. Typed validation error with `stage`. |
| 3. Contract rules (Operation 4) | Rules a schema cannot express: conditional fields, dependence on the category's `depth`, duplicates, cap, empty strings. | Drop that metric only. Log it. Keep the rest. |

Contract rules (per metric, in order):

| Rule | Check | On failure |
|---|---|---|
| K1 Text completeness | `label`, `question`, `verification`, `resolution_source.target` are non-empty after trimming. | Drop |
| K2 Value-type parameters | `number_with_unit` → `unit` set and `enum_values` empty. `enum` → ≥2 distinct non-empty `enum_values` and `unit` unset. `boolean` / `date_time` → `unit` unset and `enum_values` empty. | Drop |
| K3 Band within depth | `band = specific_attributes` only when the category's `depth = specific_attributes`. | Drop |
| K4 Tool fits band | `firecrawl` only with `band = specific_attributes`. | Drop |
| K5 No duplicate | Same `label` (case-insensitive, trimmed) already kept for this category. | Drop the later one |
| K6 Cap | More than 4 survivors in one band for one category. | Drop the extras after the 4th, in model order |

**Not checkable in code:** whether `resolution_source.target` is genuinely concrete, whether `verification` is a real obtainable evidence type, whether `question` is truly tied to this user, and whether a metric restates a fixed dimension. These are enforced by the instruction and the worked examples only. Code checks structure; it cannot judge the "cozy" case.

#### Examples, not a catalog

The instruction carries a few worked examples across different category types (for illustration, including the `ambiance` accept/reject pair). They are not a required set and are not a per-category lookup. No code path selects metrics by `taxonomy_node`.

#### Leftover flags as context

Leftover `characteristic` and `persona` flags on `resolved.ambiguity_flags` are rendered in a separate block of the user content. They are not resolved by asking the customer. When a metric addresses one of those phrases, its `question` states the single reading chosen. Mechanism 3 is excluded, so nothing else consumes them.

#### Write target

A new workflow object, separate from the category objects. `RequirementInterpretationState` gains `category_metrics: list[CategoryMetricSet]` (default empty list, empty until this component runs).

`MetricSpec` (stored dataclass; same fields as the wire metric):

| Field | Type | Content |
|---|---|---|
| `label` | `str` | As returned, trimmed. |
| `question` | `str` | As returned. |
| `value_type` | `Literal["number_with_unit", "boolean", "enum", "date_time"]` | As returned. |
| `unit` | `str \| None` | As returned. |
| `enum_values` | `list[str]` | As returned. |
| `resolution_source` | `ResolutionSource(tool, target)` | As returned. |
| `verification` | `str` | As returned. |
| `null_policy` | `Literal["null", "unknown"]` | As returned. |
| `band` | `Literal["operating_details", "specific_attributes"]` | As returned. |

`CategoryMetricSet` (one per category, in `state.category_metrics`):

| Field | Type | Content |
|---|---|---|
| `category_id` | `int` | Identity from Mechanism 2 (explicit) or Mechanism 4 (inferred). Join key. |
| `taxonomy_node` | `str` | Copied by code from the matching `ResolvedCategory` or `InferredCategory` by `category_id`. Not produced by the model. |
| `metrics` | `list[MetricSpec] \| None` | Surviving metrics for an eligible category (`[]` if none survived). `None` for a `basic_profile` category: no dynamic metrics are defined at that depth. |

`ResolvedCategory` and `InferredCategory` are unchanged by this component.

#### What this component reads

| Source | Fields used |
|---|---|
| `state.payload` | `normalized_text` |
| `state.resolved.persona_facts` | Situation and lifestyle facts |
| `state.resolved.ambiguity_flags` | Leftover `characteristic` and `persona` flags, context only |
| `state.resolved.resolved_explicit_categories` | `category_id`, `taxonomy_node`, `characteristics`, `depth`; origin = explicit |
| `state.inferred_categories` | `category_id`, `taxonomy_node`, `reasoning`, `depth`; origin = inferred |
| Instruction text | Depth scale, band rule, contract, fixed-dimension list, negative rules, examples |

Only eligible categories are sent to the model. It does not read `user_responses`, `extracted.explicit_categories` names, or any Mechanism 3 field.

#### What the model returns vs what code writes

**Model body (schema):**

| Field | Constraint |
|---|---|
| `categories` | Array. One entry per submitted eligible category. |
| `categories[].category_id` | Integer. Must echo a submitted id exactly once. |
| `categories[].metrics` | Array of metric objects (fields above). May be empty. |

**Code then:** checks the id set equals the submitted set; applies K1–K6 per metric; reports shortfalls; builds one `CategoryMetricSet` per category, copying `taxonomy_node` by `category_id`; leaves every other field unchanged.

Reuses `self._providers` and `_call_providers` with a new schema name (`metric_definition_schema`). Total provider failure raises a typed provider error with `stage`. A schema or id-set failure raises a typed validation error with `stage`. A contract-rule failure never raises.

#### Empty or thin signals

`persona_facts`, `characteristics`, and leftover flags may be empty; `reasoning` may be thin. The call still runs whenever one eligible category exists. Thin signals are not a skip and not a failure: the model still proposes contract-passing `operating_details`-band metrics tied to the category's own request or inference. It does not invent a `specific_attributes` metric without a trigger.

#### What this component does not do

- It does not assign or change `depth`.
- It does not search, retrieve, resolve, or score an amenity, and it does not call Maps, parallel web search, or firecrawl. `resolution_source` names what a later stage will use.
- It does not define the fixed dimensions and does not store them on the state.
- It does not store a facts list. A fact is a contract-passing metric whose value is resolved later.
- It does not tag priority or capture a reason (Mechanism 3 is excluded).
- It does not resolve leftover flags with the customer.
- It does not add, drop, or remap categories.
- It does not repair a failing metric (no fill, no rewrite, no clamp).

### Part 3 — Before/After state and residual gaps

**Branch A — no eligible category (call skipped)**

**Before:** both lists empty, or every category `depth = basic_profile`. `state.category_metrics = []`.
**After:** no model call. One `CategoryMetricSet` per existing category, each with `metrics = None`. (Both lists empty: `category_metrics` stays `[]`.) No failure.

**Branch B — at least one eligible category (call runs)**

**Before Mechanism 6** (state after Mechanism 5):
- Every category has `depth` stamped.
- `state.category_metrics = []`.
- `payload`, `persona_facts`, `extracted`, `user_responses`, `ambiguity_flags`, `category_resolution_passes` unchanged from Mechanism 5.

**After Mechanism 6:**
- `state.category_metrics` has one `CategoryMetricSet` per category (explicit first, then inferred).
- Eligible categories: `metrics` = the metrics that passed K1–K6, each with `band` ≤ the category's depth.
- `basic_profile` categories: `metrics = None`.
- Every other state field, including all `ResolvedCategory` / `InferredCategory` fields, unchanged.

| State field | Before M6 | After M6 (Branch B) | After M6 (Branch A) |
|---|---|---|---|
| `resolved.resolved_explicit_categories` | depth stamped | unchanged | unchanged |
| `inferred_categories` | depth stamped | unchanged | unchanged |
| `category_metrics` | `[]` | one `CategoryMetricSet` per category; `metrics` list for eligible, `None` for `basic_profile` | one per category, all `metrics = None` (or `[]` if no categories) |
| `resolved.persona_facts` / `payload` | carried | unchanged | unchanged |
| `resolved.ambiguity_flags` | leftover flags, if any | unchanged (read only) | unchanged |
| `extracted` / `user_responses` | carried | unchanged | unchanged |
| `category_resolution_passes` | from Mechanism 2 | unchanged | unchanged |

**(a) Assumptions baked from D1–D6, this feedback, and un-overridden safe defaults**

- One batched call. No predefined per-category metrics; examples only.
- Schema miss and id-set mismatch reject the whole body; contract-rule failures drop the single metric.
- Rejected metrics are logged, not stored on the state.
- Minimum per band is a reported shortfall, not enforced. Cap is 4 per band per category.
- `CategoryMetricSet` holds only `category_id`, `taxonomy_node`, `metrics`. `metrics = None` means "not eligible (basic_profile)"; `[]` means "eligible but nothing survived". This meaning of `None` is my assumption.
- `value_type` uses four token values; `resolution_source` is `{tool, target}`.
- `google_maps` is allowed for `operating_details`-band metrics only; `firecrawl` for `specific_attributes`-band only; `parallel_web_search` for both.
- The fixed-dimension constant lives beside `DepthLevel` in the schema module (location is an implementation choice).
- Empty strings are a code-side drop (K1), not a schema rejection, so one blank field does not discard every category's metrics.

**(b) Gaps vs current contracts**

- G1. `RequirementInterpretationState` has no `category_metrics`; no `MetricSpec`, `CategoryMetricSet`, wire models, schema name, instruction module, or typed errors exist.
- G2. `interpret()` ends at `run_per_category_depth_calibration`; it does not call this component.
- G3. The Mechanism 5 spec table and `depth_assignment_instruction.py` still list "contact/website" under `operating_details` and name "firecrawl/diffbot". This spec moves website to `basic_profile` and uses firecrawl only. Mechanism 5 text is not edited here and will disagree until synced.
- G4. Nothing here guarantees non-empty bands after drops. Only a logged shortfall exists.
- G5. The Mechanisms list at lines 168–193 numbers Depth Assignment as 7 and Metric Definition as 8, while the headings say 5 and 6. Out of scope here; not edited.
- G6. Semantic concreteness of `resolution_source` / `verification` is prompt-enforced only.

## Process Flow — Component: Per-Category Metric Definition

Locked constraints carried into this breakdown. They are fixed at the component level and are not reopened by any sub-component below.

- Input is the `RequirementInterpretationState` after Mechanism 5 (`depth` stamped on every category). Mechanism 3 is excluded.
- One constrained LLM call when at least one category has `depth ≠ basic_profile`; otherwise skip the call, write `metrics = None` sets, and do not fail.
- No predefined per-category metric catalog. The model defines the two dynamic bands each run; examples in the prompt are illustrative.
- Schema miss or id-set mismatch rejects the whole body. A single metric failing a contract rule is dropped and logged.
- `band` never exceeds the category's assigned depth. `firecrawl` only for the `specific_attributes` band.
- Fixed dimensions are a code constant looked up by `depth`; they are not model output and not stored on the state.
- Results are written to a separate `state.category_metrics` list of `CategoryMetricSet`, keyed by `category_id`. Category objects are not modified.
- Reuse `self._providers` and `_call_providers`. Typed provider error vs typed validation error, each with `stage`.
- This component does not search, retrieve, call any external tool, assign depth, resolve flags, or tag priority.

Sub-components

1. Metric Contract and State Object
2. Metric Definition Instruction
3. Constrained Metric Call and Body Validation
4. Contract Filter, Shortfall Report, State Write, and interpret Sequencing
5. Dummy-Provider Path Checks

Order: 1 → 2 → 3 → 4 → 5.

Sub-component 3 consumes the schema from 1 and the instruction from 2. Sub-component 4 consumes the accepted body from 3 (or takes the no-eligible-category skip). Sub-component 5 runs the assembled path end to end. The provider chain already exists from Mechanism 1 and is reused.

---

### Sub-component 1: Metric Contract and State Object

Goal of Component:
Define every typed shape this component uses: the closed wire models for the LLM body, the strict JSON schema built from them, the stored dataclasses (`MetricSpec`, `ResolutionSource`, `CategoryMetricSet`), the new `category_metrics` field on `RequirementInterpretationState`, the fixed-dimension constant by depth, the schema name, and the typed errors.

Problem It Aims to Solve:
No wire shape exists, so the model body has nothing to be constrained or validated against. No stored shape exists, so a validated metric has nowhere to be written. Without a closed set for `value_type`, `null_policy`, `tool`, and `band`, the same metric can arrive under different spellings on different runs. Without the fixed-dimension constant, later stages and the instruction each hold their own copy of what "fixed" means.

Finalized Approach:
1. Split wire and store. Closed Pydantic models for the LLM body (`MetricEntry`, `CategoryMetricsEntry`, `MetricDefinitionResult`). Dataclasses for the stored types. The strict schema is derived from the Pydantic models with the existing `_apply_strict_object_rules`. Same split as `DepthAssignmentResult` / `ResolvedCategory` and `InferredCategoriesResult` / `InferredCategory`.

Critical Decision Choices:
* Locked at component level: the metrics live in a separate `state.category_metrics` list of `CategoryMetricSet(category_id, taxonomy_node, metrics)`. `ResolvedCategory` and `InferredCategory` are not changed. There is no facts list.
* Locked: closed value sets are `value_type` (`number_with_unit`, `boolean`, `enum`, `date_time`), `null_policy` (`null`, `unknown`), `tool` (`google_maps`, `parallel_web_search`, `firecrawl`), and `band` (`operating_details`, `specific_attributes`).
* `taxonomy_node` is not in the wire body. Code copies it by `category_id`. The model never emits it.
* Which constraints the schema carries. Research result: Groq strict mode supports `type`, `properties`, `required`, `additionalProperties: false`, `enum`, `items`, `$ref`, and `anyOf`. It does not support `minLength`, `maxLength`, `minItems`, `maxItems`, or `if/then/else`. The OpenAI structured-outputs page fetched for this plan did not list its unsupported keywords. The schema therefore carries only required keys, closed objects, types, and closed enums. Empty-text, list-size, and cross-field rules are code checks in sub-component 4.
* `unit` is `str | None`. Strict mode needs the null case as `anyOf`. Confirm that `_apply_strict_object_rules` keeps every property required and leaves the null branch intact.
* `enum_values` is a list that is empty when unused. It is not nullable.
* The fixed-dimension constant is one tuple per depth. It sits beside `DepthLevel` in the schema module. The instruction reads it, so the "do not propose these" list and the constant cannot drift.
* The wire body carries no `depth`. Depth comes from state.
* Typed errors follow the existing pattern in `src/exceptions/deep_search.py`: a base `MetricDefinitionError` with `stage`, then `MetricDefinitionProviderError` and `MetricDefinitionValidationError`.
* Schema name constant: `METRIC_DEFINITION_SCHEMA_NAME = "metric_definition_schema"`.

---

### Sub-component 2: Metric Definition Instruction

Goal of Component:
Build the instruction text that makes one call define, for every submitted category, the dynamic metrics its assigned depth allows. The text holds the task statement, the depth scale and band rule, the metric contract as typed fields, the fixed-dimension list, the per-band tie rule, the decision test, the leftover-flag rule, the negative rules, the output rules, and the worked examples.

Problem It Aims to Solve:
The schema fixes the shape of a metric but says nothing about which metrics to propose. Without written rules the model can restate a fixed dimension, propose a metric like "is it cozy?" that has no enumerable value, tie a `specific_attributes` metric to nothing the customer said, or emit a band above the assigned depth. Code cannot check most of these (concreteness, tie to the user, restating a fixed dimension), so the instruction is the only place they are enforced.

Finalized Approach:
1. Rules plus worked pairs in a dedicated instruction module with a `build_metric_definition_instruction(json_schema)` function. Same pattern as `depth_assignment_instruction.py` and `inference_instruction.py`. Task statement, scale, contract, rules, and fixed worked pairs are module-level strings.

Critical Decision Choices:
* Locked: no predefined metric list per category or taxonomy group appears in the instruction as a required set. Worked examples are illustrative. The metric contract and the depth-scale approach are what make outputs consistent.
* Locked: the model defines only the `operating_details` and `specific_attributes` bands. It does not define fixed dimensions, re-assign depth, or call any tool.
* Origin (`explicit` or `inferred`) and assigned `depth` are labeled per row in user content. The model does not infer either from the node name.
* Tie rule per band. For `operating_details`, the category's own request (explicit) or `reasoning` (inferred) is a valid tie and the `question` states which. For `specific_attributes`, the `question` must point at the trigger that raised the depth.
* Decision test in the text: a resolved value must be able to change how the customer weights or ranks the category.
* Worked examples cover different taxonomy groups, show an `operating_details` metric and a `specific_attributes` metric, and include the `cozy` rejection with its `ambiance` reformulation. They are not reused as the live sample-runner seed.
* Tool text states the band limits: `google_maps` and `parallel_web_search` for `operating_details`, `parallel_web_search` and `firecrawl` for `specific_attributes`. `firecrawl` fetches page content. `parallel_web_search` fetches web search results.
* Leftover-flag rule: a metric that addresses a leftover phrase states the single reading chosen in its `question`.
* Caps are stated as a rule (at most 4 per band per category). Code enforces them in sub-component 4.
* The fixed-dimension list is rendered from the constant in sub-component 1.

---

### Sub-component 3: Constrained Metric Call and Body Validation

Goal of Component:
Assemble the user content, execute the single metric-definition call through the existing provider chain, and return either a body that matches the schema and whose `category_id` set equals the submitted set, or a typed failure. This covers Operations 1, 2, and 3.

Problem It Aims to Solve:
The response can omit a key, use a value outside a closed set, omit an id, invent an id, or repeat an id. Stamping or filtering such a body would write a metric set the model did not define for that category. A body that fails with no typed error gives the caller nothing to act on. Provider failure needs the same fallback behavior as the earlier mechanisms.

Finalized Approach:
1. Single-pass validation. Pass the schema at generation time. Validate the returned dict with `MetricDefinitionResult.model_validate`. Then compare the returned id list with the submitted id list. Either miss raises `MetricDefinitionValidationError`. Same order as `execute_depth_assignment`.

Critical Decision Choices:
* Locked: reuse `self._providers` and `_call_providers` with `stage="execute_metric_definition"`, `schema_name=METRIC_DEFINITION_SCHEMA_NAME`, and `provider_error_cls=MetricDefinitionProviderError`.
* Locked: a schema miss or an id-set mismatch rejects the whole body. Code does not fill, drop, or reorder ids.
* Locked: the contract rules K1 to K6 are not applied here. They run in sub-component 4.
* Fallback to the next provider happens only on `LLMProviderError`, including `LLMResponseTruncatedError`. It does not happen for a returned invalid body.
* Truncation risk is higher than in earlier mechanisms because the body can hold up to 8 metrics per category. The 4-per-band cap in the instruction is the only size control, since the provider adapters set no output token limit.
* User content is a JSON dump with `payload.normalized_text`, `persona_facts`, one origin-labeled and depth-labeled row per eligible category, and a separate block of leftover `characteristic` and `persona` flags.
* Only eligible categories (`depth` is `operating_details` or `specific_attributes`) are rendered and counted as submitted ids. `basic_profile` categories are not sent.
* Reuse the existing id-coverage helper pattern (`_depth_id_coverage_miss`) if its signature is generic. Otherwise add a sibling helper with the same return shape.
* Log events follow the M5 pattern: `metric_definition.validated` with verdict, and `metric_definition.rejected` with reason (`schema` or `category_id_coverage`).
* An empty `metrics` list for a category is valid at this step.

---

### Sub-component 4: Contract Filter, Shortfall Report, State Write, and interpret Sequencing

Goal of Component:
From an accepted body, apply the contract rules K1 to K6 to each metric and drop the ones that fail (Operation 4). Report shortfalls (Operation 5). Write one `CategoryMetricSet` per category to `state.category_metrics` (Operation 6). When no category is eligible, skip Operations 1 to 5 and write `None` sets. Sequence `interpret()` so this component runs immediately after Mechanism 5.

Problem It Aims to Solve:
A body can pass the schema and still hold a metric that breaks a rule the schema does not check: a blank text field, a `number_with_unit` metric with no `unit`, a `band` above the category's depth, `firecrawl` on an `operating_details` metric, a repeated label, or a fifth metric in one band. Without a filter these reach retrieval. Without the write step no later stage can read the result. Without the skip branch a request with only `basic_profile` categories still calls the model. Without an `interpret()` call the component never runs.

Finalized Approach:
1. One filter function. `apply_metric_contract(state, body)` walks each category and each metric, applies K1 to K6 in fixed order, and returns the surviving metrics per `category_id` plus a list of rejection records. A separate `write_category_metrics` builds the `CategoryMetricSet` list from the survivors.

Critical Decision Choices:
* Locked: a metric that fails a rule is dropped and logged. Nothing is repaired, rewritten, or clamped. A rule failure never raises.
* Locked: rules are K1 (text completeness), K2 (value-type parameters), K3 (band within depth), K4 (tool fits band), K5 (no duplicate label), K6 (cap of 4 per band). Order is K1 to K6. K5 and K6 count only metrics that passed the earlier rules.
* K1 and K6 are code checks because the provider schema does not carry `minLength` or `maxItems` (see sub-component 1). K2 and K4 are code checks because strict mode does not carry conditional rules. K3 needs the category's `depth` from state, which the schema does not know. K5 compares metrics with each other.
* K3 reads `depth` by `category_id` from the explicit and inferred lists.
* Rejection log record: `event: metric_definition.metric_rejected`, `category_id`, `label`, `rule`. Rejected metrics are not stored on state.
* Shortfall report: a `metric_definition.category_underspecified` event names each eligible category with zero surviving `operating_details`-band metrics, or with `depth = specific_attributes` and zero surviving `specific_attributes`-band metrics. It is not a failure.
* `CategoryMetricSet.metrics` is a list for an eligible category (empty if none survived) and `None` for a `basic_profile` category.
* `state.category_metrics` is assigned a fresh list, explicit entries first, then inferred, so a second run does not duplicate entries.
* `taxonomy_node` on each set is copied from the matching `ResolvedCategory` or `InferredCategory` by `category_id`.
* Skip branch: if both lists are empty, log `metric_definition.skipped` and leave `category_metrics` as `[]`. If every category is `basic_profile`, log the skip, write `None` sets, and build no instruction. Neither case fails.
* `ResolvedCategory`, `InferredCategory`, `payload`, `persona_facts`, `extracted`, `user_responses`, and `ambiguity_flags` are not modified.
* `interpret()` calls the new async workflow method (`run_per_category_metric_definition`) immediately after `run_per_category_depth_calibration`.

---

### Sub-component 5: Dummy-Provider Path Checks

Goal of Component:
Run a fixed set of metric-definition bodies through the assembled path (user content, call, body validation, contract filter, state write) with a dummy provider and no live API call, and report pass or fail per check.

Problem It Aims to Solve:
The schema, the id-set check, and rules K1 to K6 are only visible when a known body is pushed through sub-components 3 and 4. A live model call returns a different body on each run and cannot show that a specific bad metric is dropped while its neighbors are kept. The skip branch and the write shape (`None` versus empty list) are also only visible on a controlled input.

Finalized Approach:
1. Fake provider with recorded dict bodies. A `FakeStructuredProvider` (same shape as in `test_mechanism_5_depth.py`) returns fixture dicts. The real validate, filter, and write path runs against them. Assertions read `state.category_metrics`, log records, and raised errors.

Critical Decision Choices:
* Locked: no live provider call in these checks. A live sample runner is a separate later artifact.
* Fixture set. No categories (no call, `category_metrics` stays `[]`). All `basic_profile` (no call, `None` sets). Schema miss: a missing field. Schema miss: a value outside a closed set. Missing id. Extra id. Duplicate id. Provider failure across the chain raises the provider error. Valid mixed batch: explicit `operating_details`, explicit `specific_attributes`, inferred `basic_profile`, inferred `operating_details`.
* Per-rule fixtures, each showing the bad metric dropped and its neighbor kept: K1 blank text, K2 missing `unit`, K2 enum with one value, K3 `specific_attributes` band on an `operating_details` category, K4 `firecrawl` on an `operating_details` metric, K5 repeated label, K6 fifth metric in one band.
* Shortfall fixture: an eligible category left with an empty band produces the `category_underspecified` log record and a `[]` list, with no error.
* Write-shape assertions: `taxonomy_node` copied correctly for an explicit and an inferred category, `None` for `basic_profile`, `[]` for an eligible category with nothing surviving, explicit entries before inferred.
* Unchanged-state assertions: `ResolvedCategory`, `InferredCategory`, `payload`, `persona_facts`, `extracted`, `user_responses`, `ambiguity_flags`, and `category_resolution_passes` are equal before and after.
* User-content assertion: only eligible rows appear, each row carries origin and depth, and the leftover-flag block is present.
* Rules that live only in the instruction (concrete `resolution_source`, tie to the user, restating a fixed dimension) are not asserted as code behavior. Fixtures that already obey them are used.
* Tests are async and follow `test_mechanism_5_depth.py` (seeded post-Mechanism-5 state, `caplog` for log events). New file: `backend/tests/services/deep_search/test_mechanism_6_metrics.py`.


---

# Mechanism 7 — Specification Assembly & Priority Enforcement
## Component: Unified Per-Category Specification Assembly

Goal of Component: Combine, for every category, its reason, priority tag, assigned depth level, and metric set (baseline + purpose-fit), factual info set, into one finalized record, structured so explicit categories remain dominant over inferred ones and rigor stays consistent across categories of equal priority.

Problem It Aims to Solve: Without an enforced assembly structure, an inferred category's fields could sit alongside explicit ones with nothing guaranteeing downstream consumers treat explicit as dominant — and no check would catch a category that ended up inconsistently under-specified relative to its peers.

Approach:
Two-block assembly: explicit and inferred categories assembled into two structurally separate blocks in the output, so priority is enforced by structure rather than by a field value that could be ignored downstream.

Important instructions: Regardless of assembly structure, every category's finalized record must include all four fields — reason, priority, depth, metrics, facts info — with none omitted. A category missing any one field produces a specification the next responsibility can't fully use, and nothing downstream is positioned to catch that gap.

Critical decision chioces:
Context-specific: whether cross-category consistency is checked automatically at assembly time or left as a design guarantee of Mechanisms 4 and 5's shared logic
	Decision: Through Structured Schema

---

# Responsibility‑2: Amenity Search & Factual Data Extraction

> **Scope boundary:** R2 consumes Responsibility‑1's per‑category specification (the `predefined_metrics` + `specific_metrics` object) as its only input. It finds the real amenities in the user‑defined neighborhood, keeps only the ones that truly belong to each category, and retrieves the single‑point factual value for each metric using the tool that metric's `resolution_source` dictates. It stops at facts — it does **not** interpret requirements (R1) and does **not** judge, score, or assess amenities (the later responsibility).

## User

### Stakeholder 1: Customer (End User)

**Want (Correct‑Category Results):** every amenity returned under a category is actually that category, not an adjacent or mislabeled place. *Friction:* checking by hand means opening each map result to confirm it's really a daycare and not a play‑café or park that surfaced on a proximity/keyword match, and he still can't be sure the label is right.

**Want (Metric‑Level Factual Correctness):** the specific attribute value shown for an amenity is the true value, not a guessed or approximated one. *Friction:* verifying a single fact — does this bakery open at 7am, is the bread genuinely fresh — means reading many reviews, visiting the site, or calling, repeated across every amenity and attribute.

**Want (Data‑Point Completeness):** each value arrives whole and usable — a link that works, a number carrying its unit, a value carrying its scale — not a fragment he has to complete. *Friction:* a dead link or a bare "12" with no unit sends him back to re‑find the source himself, defeating the point of it being fetched.

**Want (Honest Absence):** *[added]* when a fact genuinely can't be found, being told it's unknown rather than shown a fabricated or falsely‑confident value. *Friction:* without this he can't tell a real "unavailable" from a silent extraction error, so he either distrusts every value or acts on one that was never verified.

**Want (Currency of Facts):** *[added]* the value reflecting the amenity's current state, since hours/prices/ratings change over time. *Friction:* he has no way to know whether an "open till 9" he read once is still accurate, so he can't rely on it for a real plan.

**Want (Display‑Ready Structure):** receiving facts already organized by category and metric so they render cleanly on the frontend. *Friction:* a raw, unsorted mix of relevant and irrelevant fields forces him to mentally sort and discard as he reads.

**Want (Non‑Redundant Set):** *[added]* being shown a few representative instances of a common type, not every single one nearby. *Friction:* a raw list of all 15 nearby cafés buries the ones worth knowing about and makes him skim all of them.

*Completeness check (wants as nouns):* Correct‑Category Results, Metric‑Level Factual Correctness, Data‑Point Completeness, Honest Absence, Currency, Display‑Ready Structure, Non‑Redundant Set.

### Stakeholder 2: Developer (system owner building/operating the extraction)

**Want (Relevance Filtering Criteria):** a dependable rule for keeping only amenities that truly belong to a category and dropping the ones the search engine wrongly surfaced. *Friction:* without defined criteria, whatever the search API returns is taken at face value, so a park returned for "daycare" flows straight into the customer's results.

**Want (Cost‑Bounded Extraction):** getting the needed facts for many amenities across many categories without tool/API spend growing uncontrollably. *Friction:* naively calling every tool for every metric of every amenity multiplies calls into a cost that makes extraction across the full set of categories, amenities, and metrics infeasible to run.

**Want (Low‑Latency Extraction):** facts returning fast enough that a search request completes in a reasonable time rather than dragging. *Friction:* a serial fetch — one amenity, one metric, one call at a time — stacks latency across the many amenities and metrics in a single run until the request is too slow to be usable.

**Want (Controlled Parallelism):** fetching independent amenity/metric facts concurrently where it pays off, without exceeding what the tools and budget allow. *Friction:* without a parallelism strategy he's stuck between slow serial calls and unbounded fan‑out that trips rate limits and blows the budget.

**Want (Efficient Parsing of Structured Returns):** predefined‑metric data that comes back structured (Google Places fields) parsed straight into the target shape with minimal transformation. *Friction:* hand‑writing extraction/normalization per field per source adds latency and becomes custom code to maintain for every metric.

**Want (Source‑Appropriate Routing):** *[added]* each metric resolved by the tool actually suited to it — structured fields from Google, unstructured facts from web search / scraping — rather than one tool forced to cover all. *Friction:* without routing, structured facts get scraped expensively or unstructured facts are demanded from an API that doesn't hold them, and both paths fail.

**Want (Mergeable Output):** *[added]* the deeper, tool‑fetched facts landing in a shape that merges cleanly into the already‑extracted baseline record for each amenity. *Friction:* if each tool writes its own shape, he has to reconcile them per amenity before anything downstream is usable.

*Completeness check:* Relevance Filtering, Cost Bound, Low Latency, Controlled Parallelism, Efficient Parsing, Source‑Appropriate Routing, Mergeable Output.

## Environment

**Facts constraining what success can look like:**

- Search APIs rank by proximity plus keyword/type match, so a category query *inherently* surfaces adjacent or mislabeled places alongside true matches — irrelevance is a property of the source, not an occasional glitch.
- Not every metric value is published anywhere retrievable; some facts simply don't exist in any source, so "found" can never be guaranteed for every metric of every amenity.
- The "neighborhood" is a user‑defined radius that varies per user and per request, so the search area is an input to honor, not a fixed constant.
- Amenity density is uneven — some categories return many instances in a small radius, others few — so candidate volume per category is unpredictable.

**Facts constraining how the solution must operate:**

- The incoming spec is already split into predefined metrics (each with a structured `resolution_source`, e.g. `places.regularOpeningHours`) and LLM‑defined metrics (each with an unstructured source, e.g. `parallel_web_search`), so the extraction path per metric is *dictated by the spec*, not freely chosen.
- Predefined metrics resolve from one structured API; LLM‑defined metrics have no structured source and must be assembled from free‑text reviews or scraped pages, so effort and reliability differ by metric, not just by amenity.
- The extraction spans many amenities × many categories × many metrics **within a single search run**, so per‑call cost and latency compound across that run rather than being paid once — the volume in one pass is what makes efficiency a design constraint.
- Each available tool (Google Places New API, LLMs, Diffbot/Firecrawl, Parallel Web Search) has its own rate limits, cost, and coverage boundary, and each covers only part of the metric space — no single tool completes the extraction alone.
- Amenity facts change over time (hours, price level, rating, availability), so a retrieved value is correct **as‑of the moment it was fetched**, not permanently.
- Travel‑based accessibility (mode, route, time) is a computation layered on top of the raw coordinates/distance the API returns, so distance data alone does not satisfy the accessibility metrics.

*Completeness check:* each fact explains why a naive version fails — taking search results at face value ships irrelevant amenities; one tool for all metrics either leaves unstructured metrics unresolved or scrapes structured ones wastefully; a serial or unbounded fetch runs too slow or too expensive across the volume of one run; and ignoring the predefined/LLM split forces bespoke parsing per field.

## Problem relevance

If the amenities returned aren't genuinely the categories the user asked for, or the facts attached to them are incomplete, stale, fabricated, or unresolved for the metrics that mattered, then the assessment built on top of this data is reasoning from a wrong or hollow foundation — and the customer is pushed back into re‑verifying every amenity himself or trusting a judgment grounded in bad facts, which defeats the purpose of the feature doing the factual legwork for him. Separately, if this extraction can't run within cost and latency bounds, a single search over the full set of categories and amenities becomes too slow or too expensive to be viable.

*Filter test:* every capability written into R2's problem statement must trace back to **(a)** yielding amenities that truly belong to each category and **(b)** producing correct, complete, appropriately‑deep, honestly‑sourced factual values per metric, **within cost/latency bounds**. Anything that interprets what the user wants (R1) or judges whether an amenity is *good* (later responsibility) is cut.

---

## Deriving the Actual Problem Statement (want → capability)

**Steps 1–3 — label each want, attach a verb + mechanism, and merge wants sharing a mechanism:**

| Want(s) | Capability (verb + mechanism) |
|---|---|
| Correct‑Category Results **+** Relevance Filtering Criteria | Filter raw search results against category‑relevance criteria so only true members of each category survive |
| Non‑Redundant Set | Narrow each category to a representative set instead of returning every instance |
| Metric‑Level Factual Correctness **+** Currency of Facts | Retrieve the true, as‑of‑fetch‑time single value for each metric and verify it per the spec's verification rule |
| Source‑Appropriate Routing **+** Efficient Parsing | Resolve each metric through the tool its `resolution_source` names — parsing structured Google fields directly, assembling LLM‑defined metrics from web search/scraping |
| Data‑Point Completeness | Return each value whole — link working, number carrying unit/scale |
| Honest Absence | Apply each metric's null policy — mark unknown when no source yields it, never fabricate |
| Display‑Ready Structure **+** Mergeable Output | Assemble facts into one structured, merge‑ready record organized by category and metric |
| Cost‑Bounded **+** Low‑Latency **+** Controlled Parallelism | *(Boundary conditions, not standalone clauses)* — operate within cost/latency bounds using bounded parallelism |

**Step 4 — environment folded in as boundary conditions:** within the user‑defined radius; per the predefined/LLM split the spec dictates; marking unknown where no source exists; computing travel‑based accessibility rather than straight‑line distance.
**Step 5 — problem relevance as filter:** every clause below traces to *relevant amenities + correct/complete/honest facts within bounds*; no interpretation or judgment clause appears.
**Step 6 — explicit & hidden requirements as source:** the per‑category specification from R1 is the input the capabilities depend on.
**Step 7 — sequenced in execution order.**

## Actual Problem Statement

Taking the per‑category specification produced by Responsibility‑1 (categories, their assigned depth, and their predefined and LLM‑defined metrics) as its only input, this responsibility must first search for amenities in each category within the user‑defined radius using the Google Places New API, then filter the raw results against category‑relevance criteria so that only places genuinely belonging to that category survive and adjacent or mislabeled ones are dropped. For each surviving amenity it must retrieve the baseline predefined metrics by parsing the structured Google Places fields directly and must compute travel‑based accessibility (mode, route, and time) rather than relying on straight‑line distance alone; and, only where the category's assigned depth calls for it, it must resolve the deeper LLM‑defined metrics through the tool each metric's `resolution_source` dictates — parallel web search and page scraping — routing every metric to the source suited to it so structured facts are never scraped wastefully and unstructured facts are never demanded from an API that cannot hold them. It must then narrow each category to a representative set rather than returning every instance found. For every metric of every retained amenity it must return the true, as‑of‑fetch‑time value complete with its unit, scale, and working link where applicable and verified per the metric's verification rule, and where no source yields a value it must mark that metric unknown under its null policy rather than fabricating one. Finally, it must assemble all retrieved facts into a single structured record per amenity, organized by category and metric and shaped so the deeper facts merge cleanly onto the baseline record and the result is ready for downstream display and assessment. All of this must operate within cost and latency bounds for a single search run, using bounded parallelism across independent amenity and metric fetches, and produces factual data only — it performs no requirement interpretation and no assessment or scoring of amenities.

*Filter check (problem relevance):* every clause traces back to producing relevant amenities and correct, complete, appropriately‑deep, honestly‑sourced factual data within cost/latency bounds. No clause interprets requirements (Responsibility‑1) or judges/scores amenities (the later responsibility).



## Workflow — Responsibility‑2: Amenity Search & Factual Data Extraction

1. Search each category on the Google Places API for correct‑category results with predefined metrics:
Request the amenities per category along with their predefined metrics, including walk, drive, and cycle travel distance/duration from Places `searchNearby` `routingSummaries` (one call per mode). Ensure every value comes back in the correct format with complete details.

2. Fetch `transit_details` from the Routes API:
Run a separate Routes API call path over the results from step 1 with `travelMode: TRANSIT` (bus, subway, and train allowed in the same call — not one call per transit mode). Extra calls are only to batch destinations against the pair cap. Transit is not bundled into the walk/drive/cycle `searchNearby` calls and is not part of the travel distance/duration metrics.

3. Parse the extracted data:
Parse the fetched values into the target shape for each amenity. Derived metrics are out of the predefined catalog and are not decided here.

4. Filter out amenities that don't genuinely belong to the category:
Drop places that surfaced in the search but aren't real members of the category, like a park returned under "daycare." This is a correctness check, kept separate from and run before the narrowing in step 5.

5. Narrow the correct pool to a non‑redundant, representative set:
Reduce over‑represented amenity types to a representative subset so the customer isn't handed every instance of a common type. Base the selection on the data completeness of each candidate.

6. Discover a website for any amenity missing one:
For narrowed amenities with no website from Google, use web search to find the official site. This gives step 7 a page to scrape when the basic profile didn't include one.

7. Get initial LLM‑defined metric information through web search:
Using the amenity's name and website, web‑search for the operating‑details and specific‑attribute metric values. This produces the first-pass value for each LLM‑defined metric.

8. Scrape the website with Firecrawl and cross‑check against the web‑search result:
Firecrawl the site for detailed information; the LLM keeps the web‑search value as correct unless the scraped site contradicts it, and still reads the scrape for any additional or more precise detail on the metric. This is what makes the final value trustworthy rather than single‑source.

9. Resolve each LLM‑defined metric to a final value using its verification rule:
Apply the metric's verification rule as the decision criteria and conform the result to the metric's specified enum values. This turns the cross‑checked evidence into one committed, schema‑valid value.

10. Apply each metric's null policy:
Where a metric's value is unknown and unavailable from any source, set it to null per that metric's policy. This keeps a genuine absence distinct from a wrong or fabricated value.

11. Structure the data into display‑ready format:
Assemble every amenity's predefined and LLM‑defined metrics into one record per amenity, organized by category and metric. The output is shaped so it can be presented to the user and consumed by the downstream assessment.


## Mechanism of Responsibility - 2: Amenity search & factual data extraction

I'll ground the approaches in current API capabilities before writing, then produce the component breakdown per the Write Guide structure.
One point needs confirming — whether transit is supported in `computeRouteMatrix`. Let me check the official doc.

Research grounded a few specifics that shape the approaches below: Places API (New) returns walk/drive/cycle/two‑wheeler travel via `routingSummaries` (requires `routingParameters.origin`, and each mode is a separate call since `routingParameters` carries one `travelMode`); **transit is not** in `routingSummaries` but **is** supported by Routes API `computeRouteMatrix` with `travelMode: TRANSIT` (subject to an origins×destinations ≤ 100 cap, so batching is required); Firecrawl `/scrape` supports schema‑guided JSON extraction (and a newer `/agent` endpoint); Parallel is the web‑search API implied by `parallel_web_search`, returning attributed excerpts with confidence.
Below is the technical process flow: the mechanisms, then each broken into buildable components per the Write Guide structure.

---
Mechanisms & Dependency Order

### Mechanism 1 — Predefined‑Metric Search & Retrieval (Final)

Units (finalized): the user supplies radius in km (default 2 km) → convert to meters for any API that needs meters. All stored/output distances are km (convert if an API returns meters) and all durations are minutes (convert Google's "###s" seconds → minutes).

Predefined‑metric catalog unchanged from the last table (reachability removed; walk/drive/cycle via routingSummaries.legs.distanceMeters / .duration; transit via Routes API), with the units rule above applied at parse.

#### Mechanism goal (ordered): (1) discover the canonical places per category → (2) enrich them with routing + transit → (3) deterministically attach and emit one typed record per amenity per category.

R2 is its own class with AmenitySearchState receiving origin and radius as inputs (D2), alongside R1's category_specs.

### Component M1.1 — Place Discovery 

Goal of Component (ordered):

(Trigger: per CategorySpec.)
Issue a Nearby Search (New) bounded by locationRestriction (circle: center state.origin, radius state.radius km → meters), includedPrimaryTypes = [mapped type], maxResultCount = 3, field mask = the basic_profile + operating_details targets + places.id. No routingParameters, no transit.
Freeze the returned places as the canonical set for that category, keyed by place.id.

Problem It Aims to Solve: Establishes the candidate amenities and the place.id identity every later step joins on; freezing the set makes enrichment and attachment deterministic.

Finalized Approach:
discovery via the Places API call Nearby Search (New) with includedPrimaryTypes.

Mandatory Sub‑Tasks Independent of Approaches Taken: field mask = exactly basic + operating targets + places.id; apply radius as a hard locationRestriction; freeze the set (no later rediscovery); dedup within a category by place_id.

#### Critical Decision Choices:

Search endpoint: Nearby Search (New) — and Nearby remains the path even on a weak/empty result (no Text‑Search fallback).
Type‑mapping granularity: one primaryType per node.
Candidate volume: maxResultCount = 3, kept configurable for future tuning.
Radius: default 2 km, hard locationRestriction, km→m conversion at call time.

##### Sub-component M1.1.a — Nearby Search Request Builder
Goal of Component: Assemble a valid Nearby Search (New) request per category, holding the locationRestriction circle, includedPrimaryTypes, maxResultCount, and the field mask.

Problem it Aims to Solve: The endpoint requires a precise request object plus a field mask that names exactly the fields to return. The field mask sets both cost and which metrics come back. Without a builder, the request is assembled ad hoc and drifts between categories.

Finalized Approach: A builder function that composes the request object field by field.

Critical Decision Choices:

Generic: field-mask construction, and request-object input validation before send (confirm origin, radius, and taxonomy_node are present and well formed).
Context-specific: the field mask carries only the basic_profile and operating_details targets plus places.id (no routingParameters, no transit, per the locked M1.1 scope). includedPrimaryTypes is set to [taxonomy_node] used directly. locationRestriction is a circle centered on state.origin with radius converted from km to meters (default 2 km). maxResultCount is set to 3 and kept as a configurable value.

##### Sub-component M1.1.b — Search Execution and Failure Handling

Goal of Component: Issue the Nearby call, apply retry on transient failure, and return the raw places array or a typed failure.

Problem it Aims to Solve: The call can fail on network or rate-limit conditions. Downstream cannot consume an unvalidated or missing response. The locked decision is that Nearby stays the path even on a weak result, so there is no alternate endpoint fallback.

Finalized Approach: Google client library call that supplies its own retry. Open verification before build: do not assume the Places client library retries the Nearby call automatically. Check the client's behavior, and if it does not retry the Nearby call, add an explicit retry wrapper around it.

Critical Decision Choices:

Generic: retry backoff intervals of 2 seconds and 3 seconds, a per-call timeout of 15 seconds, and a defined predictable error type returned on total failure.
Context-specific: retry re-issues the same Nearby request (no switch to Text Search). Execution runs through the shared async layer with 3 concurrent per-category searches. The rate-limit substrate must keep those 3 concurrent searches within the tool's limits.

##### Sub-component M1.1.c — Canonical Place Set Assembly and Within-Category Dedup

Goal of Component: Convert the raw response into the frozen canonical place set for the category, keyed by place_id, deduplicated within the category, carrying the basic and operating fields, and hold it in state.discovered_places.

Problem it Aims to Solve: Enrichment and attachment operate on a fixed set. Duplicates inside a category cause repeated enrichment calls. Without a freeze step, a later stage could re-search and change the set.

Finalized Approach: A dictionary keyed by place_id per category, stored in state.discovered_places.

Critical Decision Choices:
Generic: the collection type is the per-category place_id dictionary held in state.discovered_places.
Context-specific: the dedup key is place_id and dedup runs within a category only, not across categories (per D7). Basic and operating fields are stored as returned at this stage. Conversion to km and minutes and absence flagging are deferred to M1.3. After dedup, the set is frozen.



















### Component M1.2 — Accessibility Enrichment (Agent 2)

Goal of Component (ordered):
(Trigger: after M1.1; input = the frozen canonical places.) Walk/drive/cycle: for each of the three modes, re‑issue the Nearby search with routingParameters (origin = state.origin, travelMode = <mode>) and read routingSummaries.legs.distanceMeters / .duration, tagging each by place.id.
Transit: call Routes API computeRoutes per canonical place with origin = state.origin, destination = place.location, travelMode: TRANSIT, departureTime = now (N1), field mask routes.legs.steps.transitDetails + routes.legs.duration + routes.legs.distanceMeters; tag by place.id.
Return routing + transit results keyed by place.id; do not alter, drop, or rediscover places.

#### Problem It Aims to Solve: routingSummaries need routingParameters (excluded from discovery by design) and transit lives on a different API; both must decorate the frozen set without changing it.

#### Finalized Approach: Places API routingParameters for walk/drive/cycle; Routes API computeRoutes (per place) for transit — see the confirmation callout; every result tagged with place.id.

Mandatory Sub‑Tasks Independent of Approaches Taken: one routing search per non‑transit mode (a routingParameters block carries a single travelMode); set routingParameters.origin = state.origin; transit uses origin = state.origin, destination = place (D‑C2.5); key every result by place.id; mark a mode/transit route absent when the API returns none — never fabricate.

#### Critical Decision Choices:

Transit time anchor: departureTime = now (N1).
Transit scope: transitDetails plus transit duration/distance (N2).
Call shape: transit via computeRoutes per place (matrix can't return transitDetails; at maxResultCount = 3 per‑place cost is negligible).
Route‑absent handling: represent as absent, don't fabricate.
Origin/destination: transit origin = user origin; destinations = canonical places.

Residual implementation note (for M1.2): because routingSummaries only come back attached to a Nearby search's own results, walk/drive/cycle enrichment re‑issues the discovery search per mode and attaches by place_id; a canonical place absent from a mode's re‑search gets that mode marked absent. This is stable at maxResultCount = 3 with the identical query; if it ever proves fragile, computeRouteMatrix is the drop‑in robust alternative for those three modes (it can't be used for transit, per the callout).

### Component M1.3 — Deterministic Result Attachment & Output Contract

#### Goal of Component (ordered):

(Trigger: after M1.2.) Join routing + transit onto each canonical place by place.id, programmatically — no agent reasoning (D4.3).
Normalize units (distances → km, durations → minutes) and assemble one AmenityRecord per amenity per category (D7).
Write to state.amenity_records; flag any metric the API didn't return in _absent.

#### Problem It Aims to Solve: Results arrive from three call families in different shapes; downstream needs one predictable, versioned contract (D8).

#### Finalized Approach: deterministic join by place.id into a typed AmenityRecord.

Mandatory Sub‑Tasks Independent of Approaches Taken: join strictly by place.id; per‑category record (no cross‑category merge, D7); attach units (km / minutes); set a presence flag per metric.

#### Critical Decision Choices:

Record identity: keyed by (category_id, place_id).
Absent‑value representation: null value + _absent set.
Contract versioning: version tag on the record shape for downstream stability.

#### Output contract — AmenityRecord (one per amenity per category):

| Field | Type | Content |
|---|---|---|
| contract_version | str | schema version tag |
| category_id | int | from CategorySpec |
| taxonomy_node | str | from CategorySpec |
| place_id | str | places.id — identity/join key |
| name | str | places.displayName |
| category | str | places.primaryType |
| address | str | places.formattedAddress |
| website | str \| null | places.websiteUri |
| coordinates | {lat,lng} | places.location |
| opening_hours | obj \| null | places.regularOpeningHours |
| contact_phone | str \| null | places.internationalPhoneNumber |
| rating | float \| null | places.rating |
| review_volume | int \| null | places.userRatingCount |
| price_level | enum \| null | places.priceLevel |
| routing | map&lt;{walk,drive,cycle} → {distance_km:float\|null, duration_min:float\|null}&gt; | from per-mode routingSummaries |
| transit | {distance_km:float\|null, duration_min:float\|null, details:obj\|null} \| null | computeRoutes legs duration/distance + transitDetails |
| _absent | set[str] | metric labels the API didn't return (consumed later by C4.1) |

#### AmenitySearchState: 

origin, radius, category_specs (inputs); discovered_places, enrichment (transient), amenity_records (final output).

| State field | Before M1 | After M1.1 | After M1.2 | After M1.3 |
|---|---|---|---|---|
| origin | set | set | set | set |
| radius | set | set | set | set |
| category_specs | set | set | set | set |
| discovered_places | ∅ | populated (frozen, per category) | unchanged | unchanged |
| enrichment | ∅ | ∅ | populated (routing + transit by place_id) | discarded |
| amenity_records | ∅ | ∅ | ∅ | populated — M1 output |

### Finalized assumptions: 
radius input in km (default 2 km) → meters for APIs; all output distances km, durations minutes; transit departureTime = now; LLM reasoning used only for taxonomy→primaryType mapping (search parameterization, enrichment calls, and attachment are deterministic); type mapping cached per taxonomy_node.

---























### These Mechanisms of responsibility - 2 show what needs to be done but they are not yet finalized:
M2 — Correctness Filtering & Representative Narrowing
Component C2.1 — Category‑Correctness Filter

Goal of Component: Drop candidates that aren't genuine members of the category, leaving a pool where every member truly belongs.

Problem It Aims to Solve: Search inherently returns adjacent/mislabeled places (park under "daycare"); shipping these is the single failure the responsibility exists to prevent. Correctness ≠ volume, so it's separate and runs before the expensive M3.

Three Common Approaches:

Rule‑based on Google types (primaryType/types must intersect the taxonomy node's allowed set) + name heuristics.
LLM classifier judging member/non‑member from profile + category intent.
Hybrid: type rules as a fast gate, LLM only for ambiguous cases.

Mandatory Sub‑Tasks Independent of Approaches Taken: derive the per‑category allowed‑type set from taxonomy_node; record a drop reason for traceability.

Critical Decision Choices:

Generally mandatory: precision‑vs‑recall threshold; deterministic vs LLM; drop logging.
Problem‑context‑specific: strictness given C1.1 already type‑restricted (avoid double‑dropping valid ones); LLM‑filter cost vs value (runs before deep search, so it saves more than it costs); broad‑type categories (grocery vs convenience).
Component C2.2 — Representative Narrowing

Goal of Component: Reduce an over‑represented category to a bounded, representative subset so deep search runs on a manageable set.

Problem It Aims to Solve: Density is uneven and M3 is the expensive stage, so narrowing before it is the main cost lever; Non‑Redundant Set is a customer want.

Three Common Approaches:

Rank + top‑N by data completeness and proximity/reachability.
Diversity sampling across sub‑areas/attributes.
Threshold + cap: keep all within an accessibility threshold, capped at N.

Mandatory Sub‑Tasks Independent of Approaches Taken: define N (or cap policy) per category; deterministic tie‑break.

Critical Decision Choices:

Generally mandatory: N per category; ranking signal; determinism.
Problem‑context‑specific: narrow on completeness/proximity only (characteristic values don't exist yet) — the open decision; a possible second light narrowing after M3; how N scales with the category's depth.
M3 — LLM‑Defined Metric Resolution
Component C3.1 — Multi‑Source Evidence Acquisition

Goal of Component: For each narrowed amenity and each specific_metrics entry, assemble the raw evidence: ensure a URL (discover via web search if Google gave none), run web search for the metric's target, and scrape the official site with Firecrawl.

Problem It Aims to Solve: LLM‑defined metrics have no structured source and must be built from free text; the rule is to use both web search and Firecrawl so the value can be cross‑checked; a missing website must be discovered first.

Three Common Approaches:

Query‑per‑metric: targeted Parallel search per metric + one reused Firecrawl scrape.
Batched‑per‑amenity: one broad web search + one Firecrawl schema‑extraction pass for all metrics.
Agent‑style: Firecrawl /agent given the metric list + URLs.

Mandatory Sub‑Tasks Independent of Approaches Taken: URL resolution when websiteUri is absent; run both web search and Firecrawl (both mandated); cache the scrape so it isn't re‑fetched per metric. Search and scrape are mandatory parallel work, not alternatives.

Critical Decision Choices:

Generally mandatory: web‑search provider; Firecrawl format (markdown vs schema‑guided JSON); scrape depth (page vs crawl).
Problem‑context‑specific: query construction from each metric's question/target; how many reviews/pages to pull to satisfy verification (e.g., ≥5 reviews); freshness for currency; per‑amenity cost cap.
Component C3.2 — LLM Cross‑Check & Verification Resolution

Goal of Component: Turn the evidence into one committed, schema‑valid value per specific metric by cross‑checking web vs scrape, applying the metric's verification rule, and conforming to value_type/enum_values.

Problem It Aims to Solve: The two sources will partly agree or conflict; the value must be decided by verification, not last‑source‑wins, and must be enum/type‑valid. This is where trustworthiness is produced.

Three Common Approaches:

One constrained LLM call per amenity (all metrics + evidence + rules → structured output).
Per‑metric constrained calls (isolated context).
Two‑stage: extraction then reconciliation/verification.

Mandatory Sub‑Tasks Independent of Approaches Taken: pass verification + enum_values into the call; encode "web trusted unless the scrape contradicts it, and still read the scrape for more/precise detail"; return provenance; constrain output to the schema.

Critical Decision Choices:

Generally mandatory: one call vs per‑metric; provider + fallback (OpenAI primary / Groq fallback, matching R1); structured‑output enforcement.
Problem‑context‑specific: the contradiction‑resolution policy; confidence/provenance for the fact/assessment boundary; how "evidence insufficient for the threshold" maps toward null_policy (hand‑off to C4.1); currency weighting.
M4 — Output: Null Policy & Structured Assembly
Component C4.1 — Null‑Policy & Completeness Enforcement

Goal of Component: For every metric (predefined and specific), commit either a complete value (unit/scale/working link) or an explicit null per its null_policy, so a genuine absence is distinct from a wrong value.

Problem It Aims to Solve: Honest Absence + Data‑Point Completeness wants; metrics go missing for different reasons. Without one enforcement point, absences and partial values leak inconsistently.

Three Common Approaches:

Central validator pass over the assembled record.
Inline enforcement at C1.3 and C3.2 via a shared helper.
Schema‑level enforcement in the output model's validators.

Mandatory Sub‑Tasks Independent of Approaches Taken: validate links resolve (else null/flag); ensure unit/scale on numeric metrics; apply null_policy uniformly.

Critical Decision Choices:

Generally mandatory: where enforcement lives; link‑liveness depth; null representation.
Problem‑context‑specific: link‑validation cost vs value; "unknown" vs "not applicable"; an as‑of‑fetch‑time timestamp on volatile values.
Component C4.2 — Record Assembly & Display‑Ready Structuring

Goal of Component: Merge each amenity's predefined + specific metrics into one record, organized by category and metric, in the output schema — mergeable and ready for downstream display and assessment.

Problem It Aims to Solve: Facts arrive from different tools/stages in different shapes; without a single assembly target they can't be presented or consumed. Mergeable Output + Display‑Ready Structure wants.

Three Common Approaches:

Typed output model per amenity nested under its category.
Normalized rows (amenity, metric) for frontend + assessment to join.
Plan‑shaped document mirroring R1's per‑category object shape.

Mandatory Sub‑Tasks Independent of Approaches Taken: key by category + amenity + metric; carry provenance/timestamp; keep facts structurally separate from any later assessment field.

Critical Decision Choices:

Generally mandatory: output schema + versioning; nesting by category vs flat rows; serialization.
Problem‑context‑specific: the shape the downstream assessment consumes without reshaping; keeping the fact/assessment boundary structural; how the consolidated accessibility object is nested.












Sources: [Places routing summaries](https://developers.google.com/maps/documentation/places/web-service/routing-summary), [Nearby Search (New)](https://developers.google.com/maps/documentation/places/web-service/nearby-search), [computeRouteMatrix](https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRouteMatrix), [Transit route matrix](https://developers.google.com/maps/documentation/routes/transit-rm), [Firecrawl scrape](https://www.firecrawl.dev/blog/mastering-firecrawl-scrape-endpoint), [Parallel Search API](https://docs.parallel.ai/search/search-quickstart).







































### 3. Candidate selection (responsibility Not implemented)

**Responsibility:** Determine which amenities within each category are worth presenting.

This includes:
* Matching user-specified characteristics.
* Considering reasonable alternatives.
* Removing unnecessary duplicates or excessive results.
* Selecting a representative set.

This is different from discovery: **discovery finds what exists; selection decides what is relevant enough to continue with.**

Your workflow explicitly has this narrowing step after the deeper search. 

---

### 4. Assessment / judgment (responsibility Not implemented)

This is another very clear boundary.

**Responsibility:** Use the collected facts and metrics to determine how well each category or amenity satisfies the user's requirements.

For example:

> Facts: Gym A is 700 m away, 4.6 rated, open 24 hours.
> Assessment: Gym A is a strong match for the user's requirement for a nearby 24-hour gym.

The assessment should remain separate from the facts, while retaining the facts it was based on. This separation is explicitly part of your problem definition. 

---

### 5. Presentation (responsibility Not implemented)

**Responsibility:** Convert the resulting information into the structure the user should see.

This includes:

* Organizing by amenity category.
* Organizing by metric.
* Adjusting depth.
* Phrasing results against the user's requirements.

This should **not perform new research or make new judgments**.
