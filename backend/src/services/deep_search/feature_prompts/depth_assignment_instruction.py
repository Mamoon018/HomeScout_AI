"""Mechanism 5: the natural-language rules and worked pairs of per-category depth assignment.

Content, not logic. The three-level scale, origin floors, trigger rule, acceptance test,
and metric contract live here as instruction text. Code does not look up depth by
taxonomy node. The model returns category_id and depth only; it does not emit metrics.
"""

import json

TASK_STATEMENT = """\
You assign one depth to every submitted amenity category in a single pass. You receive the
customer's payload, persona facts, and every remaining category already labeled as explicit
or inferred. You start each category at its origin floor and escalate only when a trigger
exists. You echo every submitted category_id exactly once. You do not invent categories,
drop categories, emit metric lists, or call retrieval tools."""

DEPTH_SCALE = """\
DEPTH SCALE

Three levels exist. Higher levels include every band below them.

basic_profile — Is it here, and can I reach it, at what cost?
Contents: identity (name, category, address, website, place_id, coords) plus accessibility metrics:
travel distance and duration per mode (walk / drive / cycle), and transit travel distance and
duration (Routes API computeRouteMatrix, travelMode TRANSIT; bus, subway, and train allowed in
the same call).
Tools later stages may use: Google Maps Places (identity and walk/drive/cycle
routingSummaries) and Routes API (transit travel distance and duration). Fully Maps-resolvable.
Contract-gated: no. These dimensions are fixed and known-resolvable.

operating_details — Is it any good, and how does it run?
Contents: basic_profile plus operational dimensions (hours, contact phone, rating,
review volume, price level) plus an LLM-defined, per-category quality set. The quality set
is category-appropriate (restaurant vs gym vs school differ). Each proposed quality metric
must pass the metric contract below.
Tools later stages may use: Maps (hours, rating, ratings count, price_level, attributes)
plus parallel web search (reputation synthesis).
Contract-gated: yes for every LLM-proposed quality metric. The fixed Maps operational
dimensions are not contract-gated.

specific_attributes — Does it fit my particular situation?
Contents: user-specific metrics beyond the above — attributes the user emphasized, or that
persona / inferred reasoning shows they would need.
Tools later stages may use: parallel web search plus firecrawl on targeted pages
(official site, schedule, menu, pricing).
Contract-gated: yes. Every metric goes through the contract.

You do not call those tools. They describe what the assigned band authorizes later stages
to use. You do not emit the metrics themselves."""

FLOOR_AND_ESCALATION = """\
FLOORS AND ESCALATION

Origin is labeled on each submitted row. Do not infer origin from the node name.

Explicit floor: operating_details, always. Explicit categories never receive basic_profile.
Escalate to specific_attributes when the user named a specific attribute for that category,
or a persona / situation criterion in the input implies a judging question that
operating_details cannot answer.

Inferred floor: basic_profile, always, by default. Stay at basic_profile unless there is a
signal in the input pointing to a specific attribute of THAT inferred category. When such
a signal exists, inspect the nature of the attribute: assign operating_details if it is
operational / quality-level; assign specific_attributes if it is a narrow, user-specific
characteristic.

Nothing drops below its own floor. No trigger means stay at the floor.

How you move between levels:
1. Start at the origin floor. Explicit → operating_details. Inferred → basic_profile.
2. Escalate on an explicit trigger only — a named attribute or a persona / inferred
   criterion the current level cannot answer (see Acceptance test). For inferred
   categories, the same trigger also chooses which higher level from the attribute's
   nature. No trigger → stay at the floor.
3. The metric contract caps later fetch at the two dynamic levels. You do not run that
   gate and you do not emit metrics."""

ACCEPTANCE_TEST = """\
ACCEPTANCE TEST

Applied identically to every level. After this level's metrics would be filled, can the
user decide whether to weight this amenity as a decision factor? If the fills would still
leave them at "I know it exists but I cannot tell whether it matters," the level
under-delivers for that criterion.

That is the pass/fail bar for "the current level cannot answer," not a feeling. There is
no fetch yet, so the test is prospective: given the trigger, would the current floor's
band let the user make that decision? If no, and a trigger exists, escalate. If no trigger
exists, stay at the floor even if the band is thin — inferred categories with no
attribute-level signal remain basic_profile.

Volume of wording alone is not a trigger. Centrality of a lifestyle topic is not a trigger
unless it implies a judging criterion the floor cannot answer."""

METRIC_CONTRACT = """\
METRIC CONTRACT

This contract gates operating_details quality metrics and every specific_attributes metric
in later stages. You do not emit metrics. It is inlined so you know what the two dynamic
levels contain.

Every dynamically chosen metric must fill all six fields. If it cannot fill even one, the
metric is rejected and never fetched. basic_profile dimensions are not run through this
contract; they are fixed and Maps-resolvable.

- label: human-readable metric name.
- question: the exact decision question it answers for this user — tied, directly or
  indirectly, to their instruction or a persona fact. Direct = they asked for it.
  Indirect = a persona / inferred fact implies they would weigh it.
- value_type: one of number+unit | boolean | enum[fixed set] | date/time. Free-form prose
  as a final value is disallowed.
- resolution_source: concrete tool + target: which Maps field, or the shape of the
  web-search query, or which page type firecrawl/diffbot hits.
- verification: what evidence confirms the value.
- null_policy: what to emit if unresolved — must be null / "unknown", never guessed.

Rejection example: "is it cozy?" fails because value_type has no enumerable range,
resolution_source names nothing concrete, and verification cannot be specified.
Reformulated to pass: label ambiance; question "user wants a quiet place to work (persona:
remote worker) — is it quiet or lively?"; value_type enum[quiet, mixed, lively];
resolution_source web search + review-term frequency; verification dominant sentiment
across ≥5 reviews mentioning noise/atmosphere; null_policy "unknown"."""

SIGNAL_SOURCES = """\
TRIGGER SIGNALS

A trigger is a named attribute or a persona / inferred criterion, found in these signals,
that the current floor cannot answer under the acceptance test.

- payload: every category. Normalized customer text. A named attribute, or a situation
  criterion, that points at this category.
- characteristics: explicit categories only. Qualities already stored on the category.
  Empty list means no named attribute from extraction.
- reasoning: inferred categories only. Persona-fact evidence already stored on THAT
  inferred entry. A trigger for an inferred category must point at that inferred node,
  not at a different explicit one.
- persona_facts: every category. Situation and lifestyle facts. A criterion implied here
  can trigger escalation when the current floor cannot answer it.

Leftover characteristic and persona flags are not inputs. User responses are not inputs.
persona_facts may be empty. characteristics may be empty. reasoning may be thin. Empty or
thin signals are not a skip and not a reason to invent a trigger: explicit stays at
operating_details; inferred stays at basic_profile."""

NEGATIVE_RULES = """\
DO NOT

- Do not invent a category, drop a submitted category, or remap a taxonomy_node.
- Do not assign basic_profile to an explicit category.
- Do not infer origin from the node name. Use the origin label on each row.
- Do not emit metrics, rationale, tools, or retrieval calls. Return category_id and depth
  only.
- Do not fill a missing id, drop an extra id, or clamp an illegal depth. Echo every
  submitted category_id exactly once.
- Do not treat volume of wording or topic centrality as a trigger unless it implies a
  judging criterion the floor cannot answer.
- Do not mix inferred entries into the explicit list. Origin stays as labeled."""

OUTPUT_RULES = """\
OUTPUT

Return one JSON object matching the schema below exactly. All keys are always present.
assignments length equals the number of submitted categories.

{schema}"""

# Worked pairs: (depth input as JSON, expected DepthAssignmentResult as JSON).
# Six locked cases, on nodes the sample runner will not reuse:
# 1. explicit, no trigger → operating_details
# 2. explicit, named attribute the floor cannot answer → specific_attributes
# 3. inferred, no attribute signal → basic_profile
# 4. inferred, operational/quality signal → operating_details
# 5. inferred, narrow user-specific signal → specific_attributes
# 6. mixed batch, one of each origin, floors held where no trigger
_DEPTH_FEW_SHOT_PAIRS: tuple[tuple[dict, dict], ...] = (
    (
        {
            "payload": {
                "normalized_text": (
                    "We need a supermarket we can reach without a car. Nothing special "
                    "about the shop itself."
                )
            },
            "persona_facts": [],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "supermarket",
                    "origin": "explicit",
                    "characteristics": [],
                }
            ],
        },
        {
            "assignments": [
                {"category_id": 0, "depth": "operating_details"},
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "We train at a gym that opens before 6am and has a dedicated "
                    "powerlifting platform. Opening time and that platform are the "
                    "reason we would pick one gym over another."
                )
            },
            "persona_facts": ["trains before work on weekdays"],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "gym",
                    "origin": "explicit",
                    "characteristics": ["opens before 6am", "powerlifting platform"],
                }
            ],
        },
        {
            "assignments": [
                {"category_id": 0, "depth": "specific_attributes"},
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "We shop at a supermarket nearby. We have a four-year-old."
                )
            },
            "persona_facts": [
                "has a four-year-old who needs care during the workday",
            ],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "supermarket",
                    "origin": "explicit",
                    "characteristics": [],
                },
                {
                    "category_id": 1,
                    "taxonomy_node": "child_care_agency",
                    "origin": "inferred",
                    "reasoning": (
                        "The persona fact that they have a four-year-old who needs care "
                        "during the workday supports child_care_agency as a distinct need from "
                        "the explicit supermarket."
                    ),
                },
            ],
        },
        {
            "assignments": [
                {"category_id": 0, "depth": "operating_details"},
                {"category_id": 1, "depth": "basic_profile"},
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "We shop at a supermarket nearby. I pick up a weekly prescription "
                    "and need to know whether the pharmacy is open on Saturday."
                )
            },
            "persona_facts": [
                "takes weekly prescription medication and needs Saturday opening hours",
            ],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "supermarket",
                    "origin": "explicit",
                    "characteristics": [],
                },
                {
                    "category_id": 1,
                    "taxonomy_node": "pharmacy",
                    "origin": "inferred",
                    "reasoning": (
                        "The persona fact that they take weekly prescription medication "
                        "and need Saturday opening hours points at operating hours of "
                        "a pharmacy."
                    ),
                },
            ],
        },
        {
            "assignments": [
                {"category_id": 0, "depth": "operating_details"},
                {"category_id": 1, "depth": "operating_details"},
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "We shop at a supermarket nearby. We have a reactive dog that can "
                    "only go off-leash in a fenced area away from other dogs."
                )
            },
            "persona_facts": [
                "has a reactive dog that needs a fenced off-leash area away from other dogs",
            ],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "supermarket",
                    "origin": "explicit",
                    "characteristics": [],
                },
                {
                    "category_id": 1,
                    "taxonomy_node": "park",
                    "origin": "inferred",
                    "reasoning": (
                        "The persona fact that they have a reactive dog that can only "
                        "go off-leash in a fenced area away from other dogs is a narrow "
                        "user-specific characteristic of a park."
                    ),
                },
            ],
        },
        {
            "assignments": [
                {"category_id": 0, "depth": "operating_details"},
                {"category_id": 1, "depth": "specific_attributes"},
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "We want a cafe we can walk to. We also have a four-year-old."
                )
            },
            "persona_facts": [
                "has a four-year-old who needs care during the workday",
            ],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "cafe",
                    "origin": "explicit",
                    "characteristics": [],
                },
                {
                    "category_id": 1,
                    "taxonomy_node": "child_care_agency",
                    "origin": "inferred",
                    "reasoning": (
                        "The persona fact that they have a four-year-old who needs care "
                        "during the workday supports child_care_agency. No attribute of the "
                        "child_care_agency itself is named."
                    ),
                },
            ],
        },
        {
            "assignments": [
                {"category_id": 0, "depth": "operating_details"},
                {"category_id": 1, "depth": "basic_profile"},
            ]
        },
    ),
)


def build_depth_assignment_instruction(json_schema: dict) -> str:
    """Assemble the depth instruction: scale, floors, triggers, contract, schema, pairs."""
    return "\n\n".join(
        (
            TASK_STATEMENT,
            DEPTH_SCALE,
            FLOOR_AND_ESCALATION,
            ACCEPTANCE_TEST,
            METRIC_CONTRACT,
            SIGNAL_SOURCES,
            NEGATIVE_RULES,
            OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
            _render_examples(build_depth_assignment_few_shot_examples()),
        )
    )


def build_depth_assignment_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed depth worked input/output pairs, rendered as JSON text."""
    return tuple(
        (json.dumps(sample_input, indent=2), json.dumps(expected, indent=2))
        for sample_input, expected in _DEPTH_FEW_SHOT_PAIRS
    )


def _render_examples(examples: tuple[tuple[str, str], ...]) -> str:
    blocks = (
        f"EXAMPLE {index}\nINPUT\n{sample_input}\n\nEXPECTED OUTPUT\n{expected}"
        for index, (sample_input, expected) in enumerate(examples, start=1)
    )
    return "WORKED EXAMPLES\n\n" + "\n\n".join(blocks)
