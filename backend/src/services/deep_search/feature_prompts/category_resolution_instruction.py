"""Sub-components 4 and 5: the natural-language rules and worked pairs of Component 2A.

Content, not logic. Operation 1 (taxonomy mapping) and Operation 2 (category-flag
resolution) both belong to Component 2A, so their instruction text lives in one module. Each
`build_*` function assembles a full instruction: task statement, rules, the maintained
taxonomy inlined in full, the output schema, and worked pairs. The taxonomy is inlined so the
model chooses only from real nodes; the schema still constrains `taxonomy_node` by enum.
"""

import json

from src.services.deep_search.feature_schemas.amenity_taxonomy import render_taxonomy

# ---------------------------------------------------------------------------------------
# Operation 1 — taxonomy mapping
# ---------------------------------------------------------------------------------------

MAPPING_TASK_STATEMENT = """\
You map a customer's explicit amenity categories onto a maintained amenity-category taxonomy. You
receive the Mechanism 1 extraction (each explicit category already labeled with a category_id,
its characteristics, the ambiguity flags, and persona facts) and the full taxonomy. For each
explicit category, select the single taxonomy node that best fits what the customer meant, using
the category name, its characteristics, and the surrounding persona context. Echo only the
category_id you were handed. You do not search, score, or answer the customer; you only decide
which taxonomy node each labeled category belongs to."""

MAPPING_RULES = """\
MAPPING RULES

- Map each explicit category to exactly one node from the taxonomy below, chosen by meaning and
  context, not by surface word overlap. "a large grocery store" is a supermarket, not a
  convenience_store.
- Use the characteristics and persona facts to disambiguate scope. "somewhere to grab a quick
  coffee" is a coffee_shop; "a quiet place to read" near a mention of borrowing books is a
  library.
- Echo `category_id` from the extraction input. Do not invent an id and do not return a name.
- A category you can map confidently to one node goes in `resolved_categories` as
  `{taxonomy_node, category_id}`.
- A category you cannot confidently map to a single node has its `category_id` listed in
  `unmapped_category_ids`. It does not go in `resolved_categories`.
- Every category_id from the extraction appears in exactly one of those two lists."""

MAPPING_NEGATIVE_RULES = """\
DO NOT

- Do not invent a taxonomy node, rename one, or return anything outside the taxonomy list.
- Do not split one category across multiple nodes; each maps to exactly one node.
- Do not resolve a category by guessing when the input gives no confident basis; list its id as
  unmapped.
- Do not copy names, characteristics, persona facts, or the payload into your output; return only
  `taxonomy_node` and `category_id` per mapping, plus `unmapped_category_ids`. Everything else is
  attached programmatically by id.
- Do not drop a key. Every key in the schema is always present."""

# ---------------------------------------------------------------------------------------
# Operation 2 — category-flag resolution
# ---------------------------------------------------------------------------------------

RESOLUTION_TASK_STATEMENT = """\
You resolve category-level ambiguity flags into taxonomy nodes. You receive a list of
{flag, response} pairs: each flag is a category the customer's original wording left unclear
and already carries its category_id, and each response is the customer's answer to a
clarification question about that flag. You also receive the full taxonomy. For each pair,
select the single taxonomy node the customer means, using the flag phrase, the paired
response, and any context in them. Echo only the category_id you were handed."""

RESOLUTION_RULES = """\
RESOLUTION RULES

- Resolve every pair. Return one entry in `resolved_categories` for each {flag, response}
  pair you were given.
- Echo `category_id` from the flag. Do not invent an id and do not return a name.
- Set `provenance` to "confident" when the paired response gives clear evidence for a node.
- When the paired response is still insufficient to choose confidently, map the flag to the
  nearest most-fitting node in the taxonomy and set `provenance` to "nearest_node". Never
  leave a pair unresolved; every category flag must exit as a taxonomy node."""

RESOLUTION_NEGATIVE_RULES = """\
DO NOT

- Do not invent a taxonomy node, rename one, or return anything outside the taxonomy list.
- Do not look responses up yourself or re-pair flags; each flag is already paired with its
  own response.
- Do not return names, characteristics, or persona facts; return only `taxonomy_node`,
  `category_id`, and `provenance` per entry.
- Do not drop a key. Every key in the schema is always present."""

# ---------------------------------------------------------------------------------------
# Shared blocks
# ---------------------------------------------------------------------------------------

TAXONOMY_HEADER = """\
AMENITY-CATEGORY TAXONOMY

Map only to one of these exact nodes:"""

OUTPUT_RULES = """\
OUTPUT

Return one JSON object matching the schema below exactly. All keys are always present.

{schema}"""

# Worked pairs for Operation 1: (extraction input as JSON, expected mapping output as JSON).
_MAPPING_FEW_SHOT_PAIRS: tuple[tuple[dict, dict], ...] = (
    (
        {
            "explicit_categories": [
                {
                    "category_id": 0,
                    "name": "well-equipped gym",
                    "characteristics": ["open before 7am", "within walking distance"],
                },
                {
                    "category_id": 1,
                    "name": "large grocery store",
                    "characteristics": ["not a corner shop", "reachable without a car"],
                },
                {
                    "category_id": 2,
                    "name": "a place to get my shopping done",
                    "characteristics": ["without a long trip"],
                },
            ],
            "ambiguity_flags": [
                {
                    "phrase": "a place to get my shopping done",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                    "category_id": 2,
                },
            ],
            "persona_facts": ["cooks most nights", "only has one car between two people"],
        },
        {
            "resolved_categories": [
                {"taxonomy_node": "gym", "category_id": 0},
                {"taxonomy_node": "supermarket", "category_id": 1},
            ],
            "unmapped_category_ids": [2],
        },
    ),
    (
        {
            "explicit_categories": [
                {
                    "category_id": 0,
                    "name": "daycare",
                    "characteristics": ["within a short walk"],
                },
                {
                    "category_id": 1,
                    "name": "somewhere to run",
                    "characteristics": ["can loop around"],
                },
            ],
            "ambiguity_flags": [],
            "persona_facts": ["has a four-year-old", "runs early mornings"],
        },
        {
            "resolved_categories": [
                {"taxonomy_node": "child_care_agency", "category_id": 0},
                {"taxonomy_node": "park", "category_id": 1},
            ],
            "unmapped_category_ids": [],
        },
    ),
)

# Worked pairs for Operation 2: (pairs input as JSON, expected resolution output as JSON).
_RESOLUTION_FEW_SHOT_PAIRS: tuple[tuple[list, dict], ...] = (
    (
        [
            {
                "flag": {
                    "phrase": "a place to get my shopping done",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                    "category_id": 2,
                },
                "response": {
                    "question": (
                        "When you say a place to get your shopping done, do you mean a full "
                        "supermarket, a convenience store, or a shopping mall?"
                    ),
                    "options": ["full supermarket", "convenience store", "shopping mall"],
                    "response": "A full supermarket for a big weekly shop.",
                },
            },
            {
                "flag": {
                    "phrase": "something for the evenings",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                    "category_id": 4,
                },
                "response": {
                    "question": "What did you have in mind for the evenings?",
                    "options": ["bar", "restaurant", "not sure"],
                    "response": "Not sure really, just somewhere to go out sometimes.",
                },
            },
        ],
        {
            "resolved_categories": [
                {
                    "taxonomy_node": "supermarket",
                    "category_id": 2,
                    "provenance": "confident",
                },
                {
                    "taxonomy_node": "bar",
                    "category_id": 4,
                    "provenance": "nearest_node",
                },
            ],
        },
    ),
)


def build_taxonomy_mapping_instruction(json_schema: dict) -> str:
    """Assemble the Operation 1 instruction: mapping rules, full taxonomy, schema, pairs."""
    return "\n\n".join(
        (
            MAPPING_TASK_STATEMENT,
            MAPPING_RULES,
            MAPPING_NEGATIVE_RULES,
            f"{TAXONOMY_HEADER}\n\n{render_taxonomy()}",
            OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
            _render_examples(build_mapping_few_shot_examples()),
        )
    )


def build_flag_resolution_instruction(json_schema: dict) -> str:
    """Assemble the Operation 2 instruction: resolution rules, full taxonomy, schema, pairs."""
    return "\n\n".join(
        (
            RESOLUTION_TASK_STATEMENT,
            RESOLUTION_RULES,
            RESOLUTION_NEGATIVE_RULES,
            f"{TAXONOMY_HEADER}\n\n{render_taxonomy()}",
            OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
            _render_examples(build_resolution_few_shot_examples()),
        )
    )


def build_mapping_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed Operation 1 worked input/output pairs, rendered as JSON text."""
    return tuple(
        (json.dumps(extraction, indent=2), json.dumps(expected, indent=2))
        for extraction, expected in _MAPPING_FEW_SHOT_PAIRS
    )


def build_resolution_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed Operation 2 worked input/output pairs, rendered as JSON text."""
    return tuple(
        (json.dumps(pairs, indent=2), json.dumps(expected, indent=2))
        for pairs, expected in _RESOLUTION_FEW_SHOT_PAIRS
    )


def _render_examples(examples: tuple[tuple[str, str], ...]) -> str:
    blocks = (
        f"EXAMPLE {index}\nINPUT\n{sample_input}\n\nEXPECTED OUTPUT\n{expected}"
        for index, (sample_input, expected) in enumerate(examples, start=1)
    )
    return "WORKED EXAMPLES\n\n" + "\n\n".join(blocks)
