"""Sub-component 3: the natural-language rules and worked pairs of the extraction call.

Content, not logic. The worked examples deliberately use neutral wording rather than the
project's amenity vocabulary, because mapping a category onto that vocabulary belongs to
Component 2A and examples in taxonomy terms would pull this call toward doing it here.
"""

import json

TASK_STATEMENT = """\
You separate one customer's raw property-search requirements into four buckets in a single
pass. You do not answer the customer, summarise the text, or search for anything. You only
separate what the text already says, so that every later step can tell "something the
customer asked for" apart from "background about who the customer is"."""

BUCKET_DEFINITIONS = """\
BUCKETS

(a) explicit_categories[].name — an amenity category the customer directly names or clearly
    refers to as wanted, preferred, needed, avoided, or considered. Record it in the
    customer's own wording.

(b) explicit_categories[].characteristics — the qualities the customer states about that
    category: what kind, how close, how good, when open, and so on. They nest under the
    category they belong to, never as a category of their own. A category named with no
    qualities attached gets an empty list.

(c) ambiguity_flags — a phrase that has two or more reasonable readings which would lead to
    different categories, different characteristics, or a different scope, where the text
    gives no confident basis to pick one. Set `target` to what the phrase is about:
    "category", "characteristic", or "persona". Every flag also carries `category` and
    `characteristic`: for a "characteristic" flag, set `category` to the named category the
    quality belongs to and `characteristic` to the quality itself; for a "category" or
    "persona" flag, set both to null. Both keys are always present, using null when they do
    not apply. Flagging a phrase does not remove it from its bucket: an ambiguous category is
    still recorded in explicit_categories, and an ambiguous quality is still recorded under
    its category.

(d) persona_facts — facts about who the customer is, their situation, and their lifestyle:
    household, work pattern, transport, routine, budget, timing, and anything else that is
    background rather than a request."""

NEGATIVE_RULES = """\
DO NOT

- Do not map a category onto any predefined or standard category list, and do not rename,
  broaden, or narrow the customer's wording. "a place to get my shopping done" stays exactly
  that; it does not become "supermarket".
- Do not add a category the customer did not state. If the text only supports an inference,
  it is not an explicit category.
- Do not infer a category from unrelated context. A customer who mentions a commute has not
  named a transport category unless they asked about one.
- Do not resolve an ambiguous phrase yourself. Flag it and leave it in the customer's words.
- Do not judge, rank, or score anything, and do not invent qualities the text does not state.
- Do not drop a bucket key. An empty bucket is an empty list, never a missing key or null."""

BOUNDARY_RULES = """\
CROSS-BUCKET BOUNDARIES

- Request vs background: a phrase belongs in explicit_categories when the customer is asking
  for that category to be considered, and in persona_facts when it describes their
  circumstances. "I need a gym nearby" is a request; "I train every morning" is background.
- A named category the customer wants to avoid stays an explicit category, with the
  avoidance recorded as one of its characteristics.
- A negation or a conditional that does not name a category is a persona fact, never an
  explicit category. "We don't drive", "no interest in nightlife", and "if we get a dog we'd
  want green space" are all persona facts, because none of them puts a category into the
  request.
- A quality never stands alone. If the customer states a quality without a category, it is a
  persona fact; if it belongs to a category they named, it is a characteristic of it.
- Every phrase lands in exactly one of the three buckets, plus an ambiguity flag when it has
  competing readings.
- There is no limit on how many items a bucket may hold. Record every statement the text
  supports."""

OUTPUT_RULES = """\
OUTPUT

Return one JSON object matching the schema below exactly. All three keys are always present.

{schema}"""

# One rich input, one thin input, one carrying ambiguity, one carrying negations and a
# conditional — the four shapes the buckets have to stay separated across.
_FEW_SHOT_PAIRS: tuple[tuple[str, dict], ...] = (
    (
        "We're relocating in March because my partner starts a new job here. I work from "
        "home four days a week, so daytime quiet matters. A well-equipped gym within "
        "walking distance is the big one for me, ideally with early morning hours since I "
        "train before work. We'd also want a large grocery store close by, not just a "
        "corner shop, because we cook most nights.",
        {
            "explicit_categories": [
                {
                    "name": "gym",
                    "characteristics": [
                        "well-equipped",
                        "within walking distance",
                        "early morning hours",
                    ],
                },
                {
                    "name": "grocery store",
                    "characteristics": ["large", "close by", "not just a corner shop"],
                },
            ],
            "ambiguity_flags": [],
            "persona_facts": [
                "relocating in March",
                "partner is starting a new job in the area",
                "works from home four days a week",
                "daytime quiet matters",
                "trains before work",
                "cooks most nights",
            ],
        },
    ),
    (
        "Just need a gym and a park close by.",
        {
            "explicit_categories": [
                {"name": "gym", "characteristics": ["close by"]},
                {"name": "park", "characteristics": ["close by"]},
            ],
            "ambiguity_flags": [],
            "persona_facts": [],
        },
    ),
    (
        "I'd like a good school nearby and somewhere decent to eat. Also a place to get my "
        "shopping done without a long trip.",
        {
            "explicit_categories": [
                {"name": "school", "characteristics": ["good", "nearby"]},
                {"name": "somewhere decent to eat", "characteristics": ["decent"]},
                {
                    "name": "a place to get my shopping done",
                    "characteristics": ["without a long trip"],
                },
            ],
            "ambiguity_flags": [
                {
                    "phrase": "good school",
                    "target": "characteristic",
                    "category": "school",
                    "characteristic": "good",
                },
                {
                    "phrase": "somewhere decent to eat",
                    "target": "characteristic",
                    "category": "somewhere decent to eat",
                    "characteristic": "decent",
                },
                {
                    "phrase": "a place to get my shopping done",
                    "target": "category",
                    "category": None,
                    "characteristic": None,
                },
            ],
            "persona_facts": [],
        },
    ),
    (
        "We don't drive, so anything that needs a car is out. If we end up getting a dog "
        "we'd care about green space, but that's not decided yet. I'd rather not be right "
        "next to a busy bar.",
        {
            "explicit_categories": [
                {
                    "name": "bar",
                    "characteristics": ["busy", "would rather not be right next to one"],
                },
            ],
            "ambiguity_flags": [],
            "persona_facts": [
                "does not drive",
                "anything that requires a car is out of consideration",
                "may get a dog, not decided yet",
                "would care about green space only if they get a dog",
            ],
        },
    ),
)


def build_few_shot_examples() -> tuple[tuple[str, str], ...]:
    """The fixed worked input/output pairs, outputs rendered as JSON text."""
    return tuple(
        (customer_input, json.dumps(expected, indent=2))
        for customer_input, expected in _FEW_SHOT_PAIRS
    )
