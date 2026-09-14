"""Mechanism 4: the natural-language rules and worked pairs of persona-driven inference.

Content, not logic. Distinctness Step 1 aliases and all of Step 2 live here as instruction
text; they are not a programmatic clamp. The taxonomy is inlined so the model chooses only
from real nodes; the schema still constrains `taxonomy_node` by enum and caps the list at two.
"""

import json

from src.services.deep_search.feature_schemas.amenity_taxonomy import render_taxonomy

TASK_STATEMENT = """\
You infer additional amenity-category taxonomy nodes from persona evidence. You receive the
customer's persona facts, each resolved explicit category as its taxonomy_node plus
characteristics, the original payload, and the full taxonomy. Propose at most two nodes the
customer did not state. Each proposal must be a node in the taxonomy, must be distinct from
the explicit set and from the other inferred node, and must be backed by persona facts cited
in reasoning. Generic associations are not enough. Zero categories is valid. You do not
search, score, attach characteristics, or explain why an explicit category matters."""

EVIDENCE_RULES = """\
EVIDENCE

- Infer a node only when persona facts support it as a real information need, not a generic
  association. "has a four-year-old" can support daycare; "lives in a city" does not support
  a supermarket.
- Cite the persona facts in `reasoning`. A reader must be able to see which facts back the
  inference.
- `reasoning` is the evidence record. It is not a plausibility score and not a purpose-reason
  for the amenity. Capturing why an explicit category matters is out of scope.
- Persona facts may be empty or thin. Return an empty `inferred_categories` list. Do not
  force a category."""

DISTINCTNESS_RULES = """\
DISTINCTNESS

An inferred category is not distinct — omit it — if the information it would add is already
substantially recoverable from an explicit category or from the characteristics used to
describe that explicit category. Distinct means a genuinely new discriminating dimension, not
a new label for existing information. The same tests apply between two inferred items.

Step 1 — Same taxonomy node?
Identity, including aliases, synonyms, and trivial rewordings of the same node
(singular/plural, casing, phrasing). If the candidate is the same node as an explicit
category, or the same node as another inferred category, omit it. Do not run Step 2.

Step 2 — Different node, but same information need?
If it clears Step 1, apply all three tests. Any single yes means omit it:
1. Reconstruction: Could someone who only has the explicit category and its listed
   characteristics fully reconstruct what the inferred category is telling them? If it adds
   nothing beyond what is already derivable, omit it.
2. Discrimination: Does the inferred category ever split two items that the explicit category
   (plus its characteristics) treats identically? If it never changes how two cases are
   distinguished, omit it.
3. Directionality: Is the inferred category only a narrower subset, rephrasing, or logical
   consequence of an existing characteristic (rather than an independent axis)? If so, omit it.

If all three are no: the candidate is distinct — include it, up to the cap of two."""

NEGATION_RULE = """\
NEGATION

- A category the persona facts negate must not be inferred. "no interest in nightlife" does
  not support nightclub or bar."""

NEGATIVE_RULES = """\
DO NOT

- Do not invent a taxonomy node, rename one, or return anything outside the taxonomy list.
- Do not restate an explicit node, including by alias, synonym, or trivial rewording.
- Do not force a category when evidence is thin or every candidate fails distinctness.
  Return [].
- Do not infer characteristics, raw names, provenance, or a priority tag. Return only
  `taxonomy_node` and `reasoning` per entry.
- Do not capture why an explicit category matters.
- Do not drop a key. `inferred_categories` is always present; an empty result is an empty
  list."""

TAXONOMY_HEADER = """\
AMENITY-CATEGORY TAXONOMY

Map only to one of these exact nodes:"""

OUTPUT_RULES = """\
OUTPUT

Return one JSON object matching the schema below exactly. All keys are always present.

{schema}"""

# Worked pairs: (inference input as JSON, expected InferredCategoriesResult as JSON).
# Six locked cases: empty persona; one valid distinct node; exact-node collision omitted;
# negation omitted; two distinct nodes; Step 2 overlap (gym / fitness_center).
_INFERENCE_FEW_SHOT_PAIRS: tuple[tuple[dict, dict], ...] = (
    (
        {
            "persona_facts": [],
            "resolved_explicit_categories": [
                {
                    "taxonomy_node": "gym",
                    "characteristics": ["open before 7am"],
                }
            ],
            "payload": {
                "normalized_text": (
                    "We need a gym that opens before 7am, nothing fancy, just somewhere "
                    "to train on weekday mornings."
                ),
                "raw_text": (
                    "We need a gym that opens before 7am, nothing fancy, just somewhere "
                    "to train on weekday mornings."
                ),
            },
        },
        {"inferred_categories": []},
    ),
    (
        {
            "persona_facts": [
                "has a four-year-old who needs care during the workday",
            ],
            "resolved_explicit_categories": [
                {
                    "taxonomy_node": "gym",
                    "characteristics": ["open before 7am"],
                }
            ],
            "payload": {
                "normalized_text": (
                    "We train at a gym before 7am. We have a four-year-old who needs "
                    "care during the workday."
                ),
                "raw_text": (
                    "We train at a gym before 7am. We have a four-year-old who needs "
                    "care during the workday."
                ),
            },
        },
        {
            "inferred_categories": [
                {
                    "taxonomy_node": "daycare",
                    "reasoning": (
                        "The persona fact that they have a four-year-old who needs care "
                        "during the workday supports daycare as a distinct information "
                        "need from the explicit gym."
                    ),
                }
            ]
        },
    ),
    (
        {
            "persona_facts": ["trains every morning"],
            "resolved_explicit_categories": [
                {
                    "taxonomy_node": "gym",
                    "characteristics": ["open before 7am"],
                }
            ],
            "payload": {
                "normalized_text": (
                    "We need a gym that opens before 7am. I train every morning."
                ),
                "raw_text": (
                    "We need a gym that opens before 7am. I train every morning."
                ),
            },
        },
        {"inferred_categories": []},
    ),
    (
        {
            "persona_facts": ["no interest in nightlife", "we don't drink"],
            "resolved_explicit_categories": [
                {
                    "taxonomy_node": "supermarket",
                    "characteristics": ["reachable without a car"],
                }
            ],
            "payload": {
                "normalized_text": (
                    "We do a weekly shop at a supermarket we can reach without the car. "
                    "We're not interested in nightlife and we don't drink."
                ),
                "raw_text": (
                    "We do a weekly shop at a supermarket we can reach without the car. "
                    "We're not interested in nightlife and we don't drink."
                ),
            },
        },
        {"inferred_categories": []},
    ),
    (
        {
            "persona_facts": [
                "has a four-year-old who needs care during the workday",
                "takes weekly prescription medication",
            ],
            "resolved_explicit_categories": [
                {
                    "taxonomy_node": "gym",
                    "characteristics": ["open before 7am"],
                }
            ],
            "payload": {
                "normalized_text": (
                    "We train at a gym before 7am. We have a four-year-old who needs "
                    "care during the workday, and I pick up a weekly prescription."
                ),
                "raw_text": (
                    "We train at a gym before 7am. We have a four-year-old who needs "
                    "care during the workday, and I pick up a weekly prescription."
                ),
            },
        },
        {
            "inferred_categories": [
                {
                    "taxonomy_node": "daycare",
                    "reasoning": (
                        "The persona fact that they have a four-year-old who needs care "
                        "during the workday supports daycare, which is not recoverable "
                        "from the explicit gym."
                    ),
                },
                {
                    "taxonomy_node": "pharmacy",
                    "reasoning": (
                        "The persona fact that they take weekly prescription medication "
                        "supports pharmacy as a second distinct need from gym and daycare."
                    ),
                },
            ]
        },
    ),
    (
        {
            "persona_facts": ["works out several times a week"],
            "resolved_explicit_categories": [
                {
                    "taxonomy_node": "gym",
                    "characteristics": ["strength equipment", "open before 7am"],
                }
            ],
            "payload": {
                "normalized_text": (
                    "We need a gym with strength equipment that opens before 7am. I work "
                    "out several times a week."
                ),
                "raw_text": (
                    "We need a gym with strength equipment that opens before 7am. I work "
                    "out several times a week."
                ),
            },
        },
        {"inferred_categories": []},
    ),
)


def build_inference_instruction(json_schema: dict) -> str:
    """Assemble the inference instruction: evidence, distinctness, taxonomy, schema, pairs."""
    return "\n\n".join(
        (
            TASK_STATEMENT,
            EVIDENCE_RULES,
            DISTINCTNESS_RULES,
            NEGATION_RULE,
            NEGATIVE_RULES,
            f"{TAXONOMY_HEADER}\n\n{render_taxonomy()}",
            OUTPUT_RULES.format(schema=json.dumps(json_schema, indent=2)),
            _render_examples(build_inference_few_shot_examples()),
        )
    )


def build_inference_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed inference worked input/output pairs, rendered as JSON text."""
    return tuple(
        (json.dumps(sample_input, indent=2), json.dumps(expected, indent=2))
        for sample_input, expected in _INFERENCE_FEW_SHOT_PAIRS
    )


def _render_examples(examples: tuple[tuple[str, str], ...]) -> str:
    blocks = (
        f"EXAMPLE {index}\nINPUT\n{sample_input}\n\nEXPECTED OUTPUT\n{expected}"
        for index, (sample_input, expected) in enumerate(examples, start=1)
    )
    return "WORKED EXAMPLES\n\n" + "\n\n".join(blocks)
