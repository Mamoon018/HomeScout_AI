"""Mechanism 6: the natural-language rules and worked pairs of per-category metric definition.

Content, not logic. The band rule, tool limits, metric contract, tie rules, and decision test
live here as instruction text. Code does not look up metrics by taxonomy node. The model
returns metrics per category_id; it does not assign depth, define fixed dimensions, or fetch.
"""

import json

from src.services.deep_search.feature_schemas.schemas import (
    FIXED_DIMENSIONS_BY_DEPTH,
    MAX_METRICS_PER_BAND,
)

TASK_STATEMENT = """\
You define the dynamic metrics for every submitted amenity category in a single pass. You
receive the customer's payload, persona facts, any unresolved phrases (leftover flags), and
every eligible category labeled explicit or inferred with its assigned depth. You return one
entry per submitted category_id with the metrics that depth allows. You do not assign or
change depth, define fixed dimensions, fetch anything, or add, drop, or remap categories."""

BAND_RULE = """\
BANDS

A band is the depth level a metric belongs to. You define metrics for two bands only.
basic_profile is fixed and is never sent to you.

operating_details band: Is it any good, and how does it run, beyond the fixed dimensions?
A category-appropriate quality set (a restaurant, a gym, and a school are judged on
different things). Allowed tools: google_maps (a Maps attribute that is not already a fixed
dimension) and parallel_web_search (reputation and service facts).

specific_attributes band: Does it fit this customer's particular situation? Metrics for the
attributes the customer named, or that a persona fact or the inferred reasoning shows they
would need. Allowed tools: parallel_web_search and firecrawl (fetches the content of a
specific page such as the official site, a schedule, a menu, or a price list).

Bands are cumulative. A category with depth operating_details receives operating_details
metrics only. A category with depth specific_attributes may receive operating_details
metrics and specific_attributes metrics. Never emit a band above the category's assigned
depth. firecrawl is only for the specific_attributes band."""

METRIC_CONTRACT = """\
METRIC CONTRACT

Every metric must fill every field below. A metric that cannot fill one is dropped and
never fetched.

- label: human-readable metric name.
- question: the exact decision question this metric answers for this customer, tied to their
  request, a persona fact, or (operating_details band) the category's own request or
  inference. Say which tie applies.
- value_type: number_with_unit | boolean | enum | date_time. Free-form prose is never a
  final value. The value must be comparable.
- unit: required when value_type is number_with_unit. null otherwise.
- enum_values: at least two distinct members when value_type is enum. An empty list
  otherwise.
- resolution_source: {tool, target}. tool is google_maps, parallel_web_search, or firecrawl.
  target names something concrete: the Maps field, the shape of the search query, or the
  page type to fetch.
- verification: the evidence that confirms the value, for example "stated on the official
  site" or "dominant sentiment across at least 5 reviews".
- null_policy: null or unknown. What to emit when the value cannot be resolved. Never a guess.
- band: operating_details or specific_attributes.

Rejection example: "is it cozy?" fails because value_type has no enumerable range,
resolution_source names nothing concrete, and verification cannot be specified.
Reformulated to pass: label ambiance; question "the customer wants a quiet place to work
(persona: remote worker), is it quiet or lively?"; value_type enum; enum_values quiet, mixed,
lively; resolution_source parallel_web_search with target "review mentions of noise or
atmosphere"; verification "dominant sentiment across at least 5 reviews mentioning noise or
atmosphere"; null_policy unknown."""

TIE_RULES = """\
WHICH METRICS TO DEFINE

Decision test, applied to every metric: once resolved, would this value change how the
customer weights or ranks this category? If not, do not propose it.

operating_details band tie: the category itself is a valid tie. The customer explicitly
asked for it (explicit), or the entry's reasoning supports it (inferred). The question says
which. Propose the few quality metrics that separate a good example of that category from a
poor one for this customer's purpose.

specific_attributes band tie: the question must point at the trigger that raised the depth:
a named characteristic, a payload statement, a persona fact, or the inferred entry's
reasoning. Do not invent a specific_attributes metric without a trigger.

If a stated characteristic is already answered by a fixed dimension (for example an opening
time is answered by opening hours), do not propose a metric for it."""

LEFTOVER_FLAG_RULE = """\
LEFTOVER FLAGS

leftover_flags are phrases that stayed ambiguous. They are context only. Do not ask the
customer. When a metric addresses one of those phrases, choose a single reading and state
that reading in the metric's question."""

NEGATIVE_RULES = """\
DO NOT

- Do not assign or change depth. Every category already has one.
- Do not propose any fixed dimension. Those are fetched without metrics.
- Do not emit a band above the category's assigned depth.
- Do not emit firecrawl for an operating_details metric.
- Do not emit free-form prose as a value type, a guessed null_policy, or an empty text field.
- Do not repeat a label within one category.
- Do not invent, drop, remap, or duplicate a category_id. Echo every submitted category_id
  exactly once, with an empty metrics list if nothing passes the contract.
- Do not emit taxonomy_node, depth, or any field outside the schema."""

OUTPUT_RULES = """\
OUTPUT

Return one JSON object matching the schema below exactly. All keys are always present.
categories has one entry per submitted category_id.

{schema}"""


def _fixed_dimensions_section() -> str:
    lines = "\n".join(
        f"- {dimension}"
        for dimension in FIXED_DIMENSIONS_BY_DEPTH["specific_attributes"]
    )
    return (
        "FIXED DIMENSIONS (do not propose these)\n\n"
        "Later stages already fetch every item below for every submitted category without "
        "any metric.\n\n" + lines
    )


def _cap_section() -> str:
    return (
        "LIMITS\n\n"
        f"At most {MAX_METRICS_PER_BAND} metrics per band per category. Prefer fewer, "
        "sharper metrics."
    )


def _metric(
    label: str,
    question: str,
    value_type: str,
    resolution_tool: str,
    resolution_target: str,
    verification: str,
    band: str,
    *,
    unit: str | None = None,
    enum_values: list[str] | None = None,
    null_policy: str = "unknown",
) -> dict:
    return {
        "label": label,
        "question": question,
        "value_type": value_type,
        "unit": unit,
        "enum_values": enum_values or [],
        "resolution_source": {"tool": resolution_tool, "target": resolution_target},
        "verification": verification,
        "null_policy": null_policy,
        "band": band,
    }


# Worked pairs: (metric-definition input as JSON, expected MetricDefinitionResult as JSON).
# Illustrations only, not a required set and not a per-node lookup. Nodes are chosen to stay
# apart from the live sample runner seed.
# 1. explicit, operating_details, no trigger, quality set only
# 2. explicit, specific_attributes, a fixed dimension answers one characteristic
# 3. inferred, operating_details, tied to the inferred reasoning
# 4. mixed batch with a leftover flag read into one question
_METRIC_FEW_SHOT_PAIRS: tuple[tuple[dict, dict], ...] = (
    (
        {
            "payload": {
                "normalized_text": (
                    "We want a restaurant we can walk to for weeknight dinners."
                )
            },
            "persona_facts": [],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "restaurant",
                    "origin": "explicit",
                    "depth": "operating_details",
                    "characteristics": [],
                }
            ],
            "leftover_flags": [],
        },
        {
            "categories": [
                {
                    "category_id": 0,
                    "metrics": [
                        _metric(
                            "Typical spend per person",
                            "The customer explicitly asked for a restaurant for weeknight "
                            "dinners: what does a typical dinner cost per person?",
                            "number_with_unit",
                            "parallel_web_search",
                            "menu prices for a main course and a drink",
                            "menu prices on the official site or at least 3 listings agree",
                            "operating_details",
                            unit="USD per person",
                        ),
                        _metric(
                            "Reservation needed on weeknights",
                            "The customer explicitly asked for a restaurant for weeknight "
                            "dinners: can they walk in without a booking?",
                            "boolean",
                            "parallel_web_search",
                            "reservation policy on the booking page or reviews",
                            "stated on the official site or booking page",
                            "operating_details",
                        ),
                        _metric(
                            "Service speed",
                            "The customer explicitly asked for a restaurant for weeknight "
                            "dinners: is service usually slow or fast?",
                            "enum",
                            "parallel_web_search",
                            "review mentions of wait time and service speed",
                            "dominant sentiment across at least 5 reviews mentioning wait time",
                            "operating_details",
                            enum_values=["slow", "mixed", "fast"],
                        ),
                    ],
                }
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "I lift before work. The gym must open before 6am and have a "
                    "dedicated powerlifting platform."
                )
            },
            "persona_facts": ["trains before work on weekdays"],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "gym",
                    "origin": "explicit",
                    "depth": "specific_attributes",
                    "characteristics": ["opens before 6am", "powerlifting platform"],
                }
            ],
            "leftover_flags": [],
        },
        {
            "categories": [
                {
                    "category_id": 0,
                    "metrics": [
                        _metric(
                            "Monthly membership fee",
                            "The customer explicitly asked for a gym to train at before "
                            "work: what does membership cost per month?",
                            "number_with_unit",
                            "parallel_web_search",
                            "membership pricing for a monthly plan",
                            "price stated on the official site or at least 3 listings agree",
                            "operating_details",
                            unit="USD per month",
                        ),
                        _metric(
                            "Dedicated powerlifting platform present",
                            "The customer named a powerlifting platform as a requirement: "
                            "does the gym have a dedicated one?",
                            "boolean",
                            "firecrawl",
                            "facilities or equipment page on the official site",
                            "listed on the official facilities page",
                            "specific_attributes",
                        ),
                        _metric(
                            "Number of platforms",
                            "The customer named a powerlifting platform as a requirement: "
                            "how many platforms are there to share?",
                            "number_with_unit",
                            "firecrawl",
                            "equipment list page on the official site",
                            "count stated on the official equipment list",
                            "specific_attributes",
                            unit="platforms",
                        ),
                    ],
                }
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "We are moving to a new city. Our son needs a check-up and we "
                    "have not found a doctor yet."
                )
            },
            "persona_facts": ["has a young son who needs a routine check-up"],
            "categories": [
                {
                    "category_id": 1,
                    "taxonomy_node": "dentist",
                    "origin": "inferred",
                    "depth": "operating_details",
                    "reasoning": (
                        "The persona fact that their young son needs a routine check-up "
                        "and they have not found a provider supports a dentist."
                    ),
                }
            ],
            "leftover_flags": [],
        },
        {
            "categories": [
                {
                    "category_id": 1,
                    "metrics": [
                        _metric(
                            "New-patient appointment wait",
                            "The inferred reasoning shows a son who needs a routine "
                            "check-up soon: how many days until a new patient is seen?",
                            "number_with_unit",
                            "parallel_web_search",
                            "new patient appointment availability in reviews and booking pages",
                            "wait stated on the booking page or at least 3 reviews agree",
                            "operating_details",
                            unit="days",
                        ),
                        _metric(
                            "Treats young children",
                            "The inferred reasoning shows a young son: does the practice "
                            "see young children?",
                            "boolean",
                            "parallel_web_search",
                            "practice services description mentioning children",
                            "stated on the practice's own listing or services text",
                            "operating_details",
                        ),
                    ],
                }
            ]
        },
    ),
    (
        {
            "payload": {
                "normalized_text": (
                    "I want a hair salon with a stylist who does curly cuts, at "
                    "reasonable prices. We also have a car."
                )
            },
            "persona_facts": ["has curly hair"],
            "categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "hair_salon",
                    "origin": "explicit",
                    "depth": "specific_attributes",
                    "characteristics": ["a stylist who does curly cuts", "reasonable prices"],
                }
            ],
            "leftover_flags": [
                {
                    "phrase": "reasonable prices",
                    "target": "characteristic",
                    "category": "a hair salon",
                    "characteristic": "reasonable prices",
                }
            ],
        },
        {
            "categories": [
                {
                    "category_id": 0,
                    "metrics": [
                        _metric(
                            "Booking lead time",
                            "The customer explicitly asked for a hair salon: how soon can "
                            "a new client get an appointment?",
                            "number_with_unit",
                            "parallel_web_search",
                            "next available appointment in reviews and booking pages",
                            "stated on the booking page or at least 3 reviews agree",
                            "operating_details",
                            unit="days",
                        ),
                        _metric(
                            "Curly-cut specialist on staff",
                            "The customer named a stylist who does curly cuts and has "
                            "curly hair: does the salon list one?",
                            "boolean",
                            "firecrawl",
                            "team or services page on the official site",
                            "a stylist or a curly-cut service listed on the official site",
                            "specific_attributes",
                        ),
                        _metric(
                            "Standard haircut price",
                            "The phrase 'reasonable prices' is read as the price of a "
                            "standard haircut: what does one cost?",
                            "number_with_unit",
                            "firecrawl",
                            "price list page on the official site",
                            "price listed on the official price list",
                            "specific_attributes",
                            unit="USD",
                        ),
                    ],
                }
            ]
        },
    ),
)


def build_metric_definition_instruction(json_schema: dict) -> str:
    """Assemble the metric instruction: bands, contract, rules, limits, schema, pairs."""
    return "\n\n".join(
        (
            TASK_STATEMENT,
            BAND_RULE,
            METRIC_CONTRACT,
            _fixed_dimensions_section(),
            TIE_RULES,
            LEFTOVER_FLAG_RULE,
            _cap_section(),
            NEGATIVE_RULES,
            OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
            _render_examples(build_metric_definition_few_shot_examples()),
        )
    )


def build_metric_definition_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed metric worked input/output pairs, rendered as JSON text."""
    return tuple(
        (json.dumps(sample_input, indent=2), json.dumps(expected, indent=2))
        for sample_input, expected in _METRIC_FEW_SHOT_PAIRS
    )


def _render_examples(examples: tuple[tuple[str, str], ...]) -> str:
    blocks = (
        f"EXAMPLE {index}\nINPUT\n{sample_input}\n\nEXPECTED OUTPUT\n{expected}"
        for index, (sample_input, expected) in enumerate(examples, start=1)
    )
    return "WORKED EXAMPLES\n\n" + "\n\n".join(blocks)
