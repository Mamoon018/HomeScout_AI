"""Component 2B: the natural-language rules and worked pairs of clarification-question generation.

Content, not logic. This module owns 2B's task, rules, and few-shots; 2A's mapping and
flag-resolution text stay in category_resolution_instruction.py. The taxonomy is not inlined:
2B asks what a flagged category maps to, it does not select a node.
"""

import json

TASK_STATEMENT = """\
You generate clarification questions for amenity categories that could not be mapped to a known
type. You receive the unmapped category flags (each already labeled with a category_id and the
customer's phrase) plus grounding context: the categories that did map, the original payload,
persona facts, and the full ambiguity-flag list. For each submitted category flag, write one
question with five options that asks which amenity type the customer meant. Echo only the
category_id and category phrase you were handed. You do not search, score, or resolve the
category onto a taxonomy node; you only ask what the stated category maps to."""

RULES = """\
QUESTION RULES

- Return one question in `questions` for every submitted category flag. Do not skip a flag and
  do not add a question for a flag you were not given.
- Echo `category_id` from the submitted flag. Do not invent an id.
- Echo `category` as the flagged phrase you were handed. Do not rename it.
- Each question has exactly five `options`. One option is the literal "other" so the customer
  can describe a meaning that is not listed.
- The other four options are distinct, plausible amenity-type readings of that flagged phrase,
  grounded in the customer's wording and the surrounding persona and payload context.
- The question asks what the stated category maps to — which amenity type they meant — not
  whether they still want it, how they would rank it, or what else they might need.
- Keep questions independent. Do not bundle two flags into one question; answers must map back
  by category_id alone."""

NEGATIVE_RULES = """\
DO NOT

- Do not invent a new need, preference, or category the customer did not state.
- Do not ask a discovery, ranking, or lifestyle question. "Would a gym also be useful?" and
  "How important is this?" are out of scope.
- Do not select a taxonomy node or name a maintained node list. Mapping is someone else's job.
- Do not resolve the ambiguity yourself or omit a question because you think you know the
  answer.
- Do not copy payload text, persona facts, or resolved categories into your output; return only
  `category_id`, `category`, `question`, and `options` per entry.
- Do not drop a key. Every key in the schema is always present."""

OUTPUT_RULES = """\
OUTPUT

Return one JSON object matching the schema below exactly. All keys are always present.

{schema}"""

# Worked pairs: (flags-plus-grounding input as JSON, expected ClarificationResult as JSON).
# Flags are shown as id and phrase together. Each question has five options including "other".
_CLARIFICATION_FEW_SHOT_PAIRS: tuple[tuple[dict, dict], ...] = (
    (
        {
            "submitted_flags": [
                {"category_id": 2, "category": "a place to get my shopping done"},
            ],
            "resolved_explicit_categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "gym",
                    "raw_name": "well-equipped gym",
                    "characteristics": ["open before 7am", "within walking distance"],
                    "provenance": "confident",
                },
                {
                    "category_id": 1,
                    "taxonomy_node": "supermarket",
                    "raw_name": "large grocery store",
                    "characteristics": ["not a corner shop", "reachable without a car"],
                    "provenance": "confident",
                },
            ],
            "payload": {
                "normalized_text": (
                    "A well-equipped gym open before 7am within walking distance, a large "
                    "grocery store reachable without a car, and a place to get my shopping "
                    "done without a long trip."
                ),
                "raw_text": (
                    "A well-equipped gym open before 7am within walking distance, a large "
                    "grocery store reachable without a car, and a place to get my shopping "
                    "done without a long trip."
                ),
            },
            "persona_facts": ["cooks most nights", "only has one car between two people"],
            "ambiguity_flags": [
                {
                    "phrase": "a place to get my shopping done",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                    "category_id": 2,
                },
            ],
        },
        {
            "questions": [
                {
                    "category_id": 2,
                    "category": "a place to get my shopping done",
                    "question": (
                        "When you say a place to get your shopping done, which of these is "
                        "closest to what you meant?"
                    ),
                    "options": [
                        "a full supermarket for a weekly shop",
                        "a small convenience store or corner shop",
                        "a shopping mall with several stores",
                        "a farmers market or specialist food shop",
                        "other",
                    ],
                }
            ]
        },
    ),
    (
        {
            "submitted_flags": [
                {"category_id": 3, "category": "a place to play"},
                {"category_id": 4, "category": "something for the evenings"},
            ],
            "resolved_explicit_categories": [
                {
                    "category_id": 0,
                    "taxonomy_node": "child_care_agency",
                    "raw_name": "daycare",
                    "characteristics": ["within a short walk"],
                    "provenance": "confident",
                },
            ],
            "payload": {
                "normalized_text": (
                    "A daycare within a short walk, a place to play without a long trip "
                    "because I like sports, and something for the evenings."
                ),
                "raw_text": (
                    "A daycare within a short walk, a place to play without a long trip "
                    "because I like sports, and something for the evenings."
                ),
            },
            "persona_facts": ["has a four-year-old", "likes sports", "not particularly interested in nightlife"],
            "ambiguity_flags": [
                {
                    "phrase": "a place to play",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                    "category_id": 3,
                },
                {
                    "phrase": "something for the evenings",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                    "category_id": 4,
                },
            ],
        },
        {
            "questions": [
                {
                    "category_id": 3,
                    "category": "a place to play",
                    "question": (
                        "When you say a place to play, which of these is closest to what "
                        "you meant?"
                    ),
                    "options": [
                        "a park with space to run or play sports",
                        "a playground for children",
                        "a sports complex or recreation centre",
                        "an indoor play centre",
                        "other",
                    ],
                },
                {
                    "category_id": 4,
                    "category": "something for the evenings",
                    "question": (
                        "When you say something for the evenings, which of these is closest "
                        "to what you meant?"
                    ),
                    "options": [
                        "a restaurant for eating out",
                        "a cafe that stays open later",
                        "a cinema or theatre",
                        "a bar or pub",
                        "other",
                    ],
                },
            ]
        },
    ),
)


def build_clarification_questions_instruction(json_schema: dict) -> str:
    """Assemble the 2B instruction: rules, closed schema, two worked pairs. No taxonomy."""
    return "\n\n".join(
        (
            TASK_STATEMENT,
            RULES,
            NEGATIVE_RULES,
            OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
            _render_examples(build_clarification_few_shot_examples()),
        )
    )


def build_clarification_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed 2B worked input/output pairs, rendered as JSON text."""
    return tuple(
        (json.dumps(sample_input, indent=2), json.dumps(expected, indent=2))
        for sample_input, expected in _CLARIFICATION_FEW_SHOT_PAIRS
    )


def _render_examples(examples: tuple[tuple[str, str], ...]) -> str:
    blocks = (
        f"EXAMPLE {index}\nINPUT\n{sample_input}\n\nEXPECTED OUTPUT\n{expected}"
        for index, (sample_input, expected) in enumerate(examples, start=1)
    )
    return "WORKED EXAMPLES\n\n" + "\n\n".join(blocks)
