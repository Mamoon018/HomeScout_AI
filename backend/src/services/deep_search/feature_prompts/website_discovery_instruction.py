"""R3.M1.3 — instruction content for the two website-discovery turns (Stage 1).

Content, not logic. Two turns, two builders:

1. `build_discovery_search_instruction(name, address)` — the system instruction for the
   `web_search` tool turn, where the LLM builds the search `objective` + `search_queries` (the one
   place in the flow where the LLM chooses the search arguments). The full `address` is passed
   verbatim and the instruction directs the model to use *only* the postal code for locality
   scoping; the app parses nothing.
2. `build_website_selection_instruction(name, address, candidates, json_schema)` — the system
   instruction for the structured selection turn (no tools), where the model returns a single
   candidate `id` or the `none` sentinel — never a URL.

Both mirror the style of the other `feature_prompts/` modules: task statement + rules as module
constants, assembled by the `build_*` functions. The anti-hallucination guarantee is structural
(id-indirection in R3.M1.3), so these instructions carry the *judgment* rules, not enforcement.
"""

import json

from src.services.deep_search.feature_schemas.schemas import DiscoveryCandidate

# ---------------------------------------------------------------------------------------
# Turn 1 — the web_search tool turn (LLM builds the query)
# ---------------------------------------------------------------------------------------

_DISCOVERY_TASK_STATEMENT = """\
You locate the single official first-party website of the amenity named below. Call the web_search
tool exactly once to find it. You do not answer in prose and you do not pick a site yet — your only
job on this turn is to issue one good web search that would surface the amenity's own site."""

_DISCOVERY_QUERY_RULES = """\
SEARCH RULES

- Make exactly one web_search tool call. Do not answer in text.
- Set `objective` to a short statement of what you are finding (the amenity's official website).
- Set `search_queries` to one to three concise keyword queries, 3-6 words each. Two or three
  diverse queries are better than one. Search operators are allowed.
- Scope the search to the right place using ONLY the postal code from the address below. Do not
  parse or restate the street address; just use the postal code as a locality hint in a query.
- If the address has no postal code (some rural or international addresses), degrade in this order:
  use the locality / city name instead; and if there is no usable locality either, search on the
  amenity name alone. A missing postal code must never stop you from searching.
- Target the amenity's own official site (its homepage), not a directory, social, maps, or review
  page — those are filtered out on the next turn, so a query that favors the official site helps."""


def build_discovery_search_instruction(name: str | None, address: str | None) -> str:
    """Assemble the system instruction for the discovery web_search turn.

    The amenity `name` and the full `address` are given verbatim; the model builds the query and
    uses only the postal code for locality scoping (with the documented degrade).
    """
    identity = {
        "amenity_name": name if name else "(name unavailable)",
        "address_verbatim": address if address else "(address unavailable)",
    }
    return "\n\n".join(
        [
            _DISCOVERY_TASK_STATEMENT,
            _DISCOVERY_QUERY_RULES,
            "AMENITY\n" + json.dumps(identity, ensure_ascii=False, indent=2),
        ]
    )


# ---------------------------------------------------------------------------------------
# Turn 2 — the structured selection turn (no tools; returns a candidate id or null)
# ---------------------------------------------------------------------------------------

_SELECTION_TASK_STATEMENT = """\
You are shown the web-search results for an amenity, each as a candidate with an opaque `id`, its
title, its url, and a snippet. Decide which single candidate is the amenity's OWN first-party
official website, and return that candidate's `id`. If none of the candidates is the amenity's own
official site, return null. You never write a URL — you only name a candidate id (or null)."""

_SELECTION_JUDGMENT_RULES = """\
SELECTION RULES

- Judge each candidate against the amenity identity (name, locality, and the amenity's address).
  The snippet and title are your evidence; the url is shown only to help you judge.
- Return the `id` of the amenity's own first-party official site — the homepage the business itself
  runs. This is a binary decision: a first-party official site, or nothing.
- Return null if the best you can find is a social page (Facebook, Instagram, ...), an aggregator or
  directory/listing (Yelp, TripAdvisor, yellow pages, booking/ordering platforms), a maps page, or a
  review page. There is no "aggregator is good enough" option — if it is not the amenity's own site,
  return null.
- Return null when you are not confident a candidate is this exact amenity's official site. An
  unconfirmed guess is worse than null: a wrong site is crawled later as if it were official.
- `selected_id` must be exactly one of the candidate ids shown below, or null. Never invent an id
  and never return a url."""


def _render_candidates(candidates: tuple[DiscoveryCandidate, ...]) -> str:
    """Render the indexed candidates as a compact, readable block for the selection turn."""
    if not candidates:
        return "(no candidates — the search returned no selectable results)"
    lines: list[str] = []
    for candidate in candidates:
        title = candidate.title or "(no title)"
        snippet = candidate.text or "(no snippet)"
        lines.append(
            f"- id: {candidate.id}\n"
            f"  title: {title}\n"
            f"  url: {candidate.url}\n"
            f"  snippet: {snippet}"
        )
    return "\n".join(lines)


def build_website_selection_instruction(
    name: str | None,
    address: str | None,
    candidates: tuple[DiscoveryCandidate, ...],
    json_schema: dict,
) -> str:
    """Assemble the system instruction for the structured selection turn.

    Carries the amenity identity, the rendered candidate list, the selection rules, and the output
    schema. The model returns `{selected_id}` (a candidate id) or `{selected_id: null}`.
    """
    identity = {
        "amenity_name": name if name else "(name unavailable)",
        "address_verbatim": address if address else "(address unavailable)",
    }
    return "\n\n".join(
        [
            _SELECTION_TASK_STATEMENT,
            _SELECTION_JUDGMENT_RULES,
            "AMENITY\n" + json.dumps(identity, ensure_ascii=False, indent=2),
            "CANDIDATES\n" + _render_candidates(candidates),
            "OUTPUT SCHEMA\n" + json.dumps(json_schema, indent=2),
        ]
    )
