"""R3.M1.1 — deterministic code-path tests for the tool catalog builder and the call guard.

Planned with the `backend-test-writer` skill. No live MCP, LLM, or network: the only fake is a
hand-built `RawToolDefinition` standing in for the non-deterministic live `tools/list` payload —
everything that can actually be wrong runs for real (the real policy table, the real catalog
builder, the real `jsonschema.Draft202012Validator`, and the real catalog feeds the real guard).
Each test asserts an observable outcome (the derived schema, the returned `GuardDecision`, or a
raised exception), not an interaction, so the set survives refactors that preserve behavior.

Behaviour map (one representative case per equivalence class):
  build_tool_catalog  — allowlist + injection per context, $ref/$defs transitive carrying,
                        raw immutability, and every fail-before-LLM raise.
  guard_proposed_calls — the ordered pipeline (structure → catalog → decode → schema → validator),
                        all-errors-collected, dependent-check skipping, all-or-nothing accept,
                        and the metric-label validator in both directions.
"""

from copy import deepcopy

import pytest

from src.clients.llm_provider import ToolCall
from src.clients.mcp_tools import RawToolDefinition
from src.exceptions.deep_search import MetricResolutionValidationError
from src.services.deep_search.phase_tool_catalog import (
    build_rejection_outcomes,
    build_tool_catalog,
    guard_proposed_calls,
    metric_label_membership_validator,
    prepare_admitted_calls,
    sanitize_replay_message,
)


# --------------------------------------------------------------------------------------------------
# Fixtures — hand-built raw tool definitions (the only stand-in for the live tools/list payload).
# --------------------------------------------------------------------------------------------------
def _web_search_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "objective": {"type": "string", "description": "the goal"},
            "search_queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "queries",
            },
            # An app/extra field the allowlist must drop (the control boundary under test).
            "session_id": {"type": "string"},
        },
        "required": ["objective", "search_queries"],
        "additionalProperties": True,
    }


def _firecrawl_scrape_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "formats": {"type": "array", "items": {"type": "string"}},
            "onlyMainContent": {"type": "boolean"},
        },
        "required": ["url"],
    }


def _firecrawl_map_schema() -> dict:
    return {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}


def _raw_defs(web_schema: dict | None = None) -> dict:
    return {
        "parallel": {
            "web_search": RawToolDefinition(
                name="web_search",
                description="search the web",
                input_schema=web_schema if web_schema is not None else _web_search_schema(),
            )
        },
        "firecrawl": {
            "firecrawl_map": RawToolDefinition(
                "firecrawl_map", "map a site", _firecrawl_map_schema()
            ),
            "firecrawl_scrape": RawToolDefinition(
                "firecrawl_scrape", "scrape a page", _firecrawl_scrape_schema()
            ),
        },
    }


def _params(catalog: list[dict]) -> dict:
    return catalog[0]["function"]["parameters"]


# ==================================================================================================
# build_tool_catalog — allowlist / injection per context (happy paths + boundaries).
# ==================================================================================================
def test_website_discovery_exposes_only_objective_and_queries():
    """website_discovery derives a web_search tool exposing exactly the two allowlisted fields."""
    catalog = build_tool_catalog(_raw_defs(), "website_discovery")
    assert [t["function"]["name"] for t in catalog] == ["web_search"]
    params = _params(catalog)
    assert set(params["properties"]) == {"objective", "search_queries"}
    assert "session_id" not in params["properties"]  # app/extra field dropped
    assert "metric_label" not in params["properties"]  # discovery never adds a label
    assert params["required"] == ["objective", "search_queries"]
    assert params["additionalProperties"] is False
    assert params["properties"]["search_queries"]["minItems"] == 1  # ≥1 query enforced


def test_metric_web_search_adds_required_metric_label():
    """metric_web_search keeps the search fields and injects metric_label as a required string."""
    params = _params(build_tool_catalog(_raw_defs(), "metric_web_search"))
    assert set(params["properties"]) == {"objective", "search_queries", "metric_label"}
    assert params["properties"]["metric_label"]["type"] == "string"
    assert "metric_label" in params["required"]


def test_metric_scrape_drops_url_injects_id_and_label_list():
    """metric_scrape exposes only the app-defined id + metric_label list; url/formats never leak."""
    params = _params(build_tool_catalog(_raw_defs(), "metric_scrape"))
    assert set(params["properties"]) == {"id", "metric_label"}  # url/formats/onlyMainContent dropped
    assert params["properties"]["metric_label"]["type"] == "array"
    assert params["properties"]["metric_label"]["items"]["type"] == "string"
    assert set(params["required"]) == {"id", "metric_label"}
    assert params["additionalProperties"] is False


def test_site_map_has_no_llm_settable_arguments():
    """site_map exposes an empty parameter object — the homepage url is injected after admission."""
    params = _params(build_tool_catalog(_raw_defs(), "site_map"))
    assert params["properties"] == {}
    assert params["required"] == []
    assert params["additionalProperties"] is False


# --------------------------------------------------------------------------------------------------
# build_tool_catalog — $ref / $defs transitive preservation and raw immutability.
# --------------------------------------------------------------------------------------------------
def _ref_web_schema() -> dict:
    """search_queries expressed via a $ref chain, to prove transitive $defs carrying."""
    return {
        "type": "object",
        "properties": {
            "objective": {"type": "string"},
            "search_queries": {"$ref": "#/$defs/QueryList"},
        },
        "required": ["objective", "search_queries"],
        "$defs": {
            "QueryList": {"type": "array", "items": {"$ref": "#/$defs/Query"}},
            "Query": {"type": "string"},
            "Unused": {"type": "number"},  # not referenced → must NOT be carried
        },
    }


def test_ref_fields_carry_transitive_defs_only():
    """A retained $ref carries exactly its transitive $defs, preserved (not inlined), + minItems."""
    params = _params(build_tool_catalog(_raw_defs(_ref_web_schema()), "website_discovery"))
    assert set(params["$defs"]) == {"QueryList", "Query"}  # Unused dropped
    assert params["properties"]["search_queries"]["$ref"] == "#/$defs/QueryList"  # not inlined
    assert params["properties"]["search_queries"]["minItems"] == 1  # sibling minimum added


def test_raw_definitions_are_not_mutated():
    """Derivation runs on a deep copy — the caller's raw definition is byte-for-byte unchanged."""
    raw = _raw_defs(_ref_web_schema())
    snapshot = deepcopy(raw)
    build_tool_catalog(raw, "website_discovery")
    assert raw == snapshot


# --------------------------------------------------------------------------------------------------
# build_tool_catalog — construction failures raise before any LLM call (no fallback, no invention).
# --------------------------------------------------------------------------------------------------
def test_missing_server_raises():
    raw = _raw_defs()
    del raw["parallel"]
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(raw, "website_discovery")


def test_missing_tool_raises():
    raw = _raw_defs()
    del raw["parallel"]["web_search"]
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(raw, "website_discovery")


def test_missing_kept_field_raises():
    schema = _web_search_schema()
    del schema["properties"]["search_queries"]
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


def test_type_incompatible_search_queries_raises():
    schema = _web_search_schema()
    schema["properties"]["search_queries"] = {"type": "string"}  # not an array of strings
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


def test_unresolvable_local_ref_raises():
    schema = _web_search_schema()
    schema["properties"]["search_queries"] = {"$ref": "#/$defs/Missing"}  # no $defs at all
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


def test_unsupported_external_ref_raises():
    schema = _ref_web_schema()
    schema["properties"]["search_queries"] = {"$ref": "https://example.com/schema.json"}
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


def test_unknown_context_raises():
    """An unrecognised context is a catalog-construction failure, not a silent empty catalog."""
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(), "not_a_real_context")  # type: ignore[arg-type]


# ==================================================================================================
# guard_proposed_calls — structure, catalog, decode, schema (the ordered pipeline).
# ==================================================================================================
def _discovery_catalog() -> list[dict]:
    return build_tool_catalog(_raw_defs(), "website_discovery")


def _ok_call(call_id: str = "c1", objective: str = "find site") -> ToolCall:
    return ToolCall(
        id=call_id,
        name="web_search",
        arguments='{"objective": "%s", "search_queries": ["a query"]}' % objective,
    )


def test_no_calls_is_no_tool_calls_null_category():
    decision = guard_proposed_calls([], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert not decision.validated_calls
    assert len(decision.errors) == 1
    err = decision.errors[0]
    assert err.reason_code == "no_tool_calls"
    assert err.category is None  # the one null-category rule
    assert err.call_index is None and err.field_path is None


def test_accept_preserves_order_and_decoded_arguments():
    calls = [_ok_call("c1", "first"), _ok_call("c2", "second")]
    decision = guard_proposed_calls(calls, _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "accepted"
    assert [v.tool_call_id for v in decision.validated_calls] == ["c1", "c2"]  # original order
    assert decision.validated_calls[0].arguments == {
        "objective": "first",
        "search_queries": ["a query"],
    }


def test_arguments_not_normalized():
    """Accepted arguments are returned verbatim — no trim, no dedup (spec: preserve values)."""
    call = ToolCall(
        id="c1",
        name="web_search",
        arguments='{"objective": "  spaced  ", "search_queries": ["  a  ", "a"]}',
    )
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "accepted"
    assert decision.validated_calls[0].arguments["objective"] == "  spaced  "
    assert decision.validated_calls[0].arguments["search_queries"] == ["  a  ", "a"]


def test_missing_id_is_invalid_structure_and_skips_schema():
    """A structural failure is a prerequisite — the dependent schema check does not also fire."""
    call = ToolCall(id="", name="web_search", arguments='{"objective": "x"}')  # also schema-invalid
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert len(decision.errors) == 1  # schema check skipped because the prereq failed
    assert decision.errors[0].category == "invalid_call_structure"
    assert decision.errors[0].reason_code == "missing_tool_call_id"


def test_duplicate_ids_are_invalid_structure():
    calls = [_ok_call("dup"), _ok_call("dup")]
    decision = guard_proposed_calls(calls, _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert {e.reason_code for e in decision.errors} == {"duplicate_tool_call_id"}
    assert all(e.category == "invalid_call_structure" for e in decision.errors)


def test_missing_name_is_invalid_structure():
    """A present id but absent name is the third structural branch → invalid_call_structure."""
    call = ToolCall(id="c1", name="", arguments='{"objective": "x", "search_queries": ["q"]}')
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert decision.errors[0].category == "invalid_call_structure"
    assert decision.errors[0].reason_code == "missing_tool_name"


def test_out_of_catalog_tool():
    call = ToolCall(id="c1", name="firecrawl_scrape", arguments="{}")
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert decision.errors[0].category == "out_of_catalog"
    assert decision.errors[0].reason_code == "out_of_catalog"


def test_malformed_argument_json():
    call = ToolCall(id="c1", name="web_search", arguments="{not json")
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.errors[0].reason_code == "invalid_argument_json"
    assert decision.errors[0].category == "in_catalog"
    assert decision.errors[0].field_path == "arguments"


def test_non_object_arguments():
    call = ToolCall(id="c1", name="web_search", arguments="[1, 2]")  # valid JSON, not an object
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.errors[0].reason_code == "invalid_argument_json"
    assert decision.errors[0].category == "in_catalog"


def test_schema_failure_is_in_catalog_with_field_path():
    """Missing a required field + an extra field both surface as in_catalog with stable reasons."""
    call = ToolCall(
        id="c1", name="web_search", arguments='{"search_queries": ["q"], "nope": 1}'
    )
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert all(e.category == "in_catalog" for e in decision.errors)
    assert any(e.reason_code == "missing_required_argument" for e in decision.errors)
    assert any(e.reason_code == "unexpected_argument" for e in decision.errors)


def test_wrong_argument_type_maps_to_invalid_argument_type():
    """A type violation maps to the stable `invalid_argument_type` reason with a field path."""
    call = ToolCall(
        id="c1", name="web_search", arguments='{"objective": 7, "search_queries": ["q"]}'
    )
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    bad = [e for e in decision.errors if e.reason_code == "invalid_argument_type"]
    assert bad and bad[0].category == "in_catalog"
    assert bad[0].field_path == "arguments.objective"


def test_empty_search_queries_is_too_few_items():
    """The builder's minItems:1 is actually enforced end-to-end: an empty list is rejected."""
    call = ToolCall(
        id="c1", name="web_search", arguments='{"objective": "o", "search_queries": []}'
    )
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert any(e.reason_code == "too_few_items" for e in decision.errors)
    assert all(e.category == "in_catalog" for e in decision.errors)


def test_all_errors_collected_across_calls():
    """Both sibling calls are inspected — errors are not reported first-only."""
    calls = [
        ToolCall(id="c1", name="unknown_tool", arguments="{}"),
        ToolCall(id="c2", name="web_search", arguments="{bad json"),
    ]
    decision = guard_proposed_calls(calls, _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert {e.call_index for e in decision.errors} == {0, 1}


# --------------------------------------------------------------------------------------------------
# guard_proposed_calls — metric-label validator (both directions) and whole-message rejection.
# --------------------------------------------------------------------------------------------------
def _metric_catalog() -> list[dict]:
    return build_tool_catalog(_raw_defs(), "metric_web_search")


def _metric_call(call_id: str, label: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        name="web_search",
        arguments='{"objective": "o", "search_queries": ["q"], "metric_label": "%s"}' % label,
    )


def test_invalid_label_rejects_whole_message_and_withholds_sibling():
    """One out-of-set label rejects the whole message; the valid sibling is withheld, not admitted."""
    calls = [_metric_call("c1", "ticket_price"), _metric_call("c2", "wheelchair_access")]
    ctx = {"metric_labels": ["ticket_price", "opening_hours"]}
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", ctx)
    assert decision.decision == "rejected"
    assert not decision.validated_calls  # valid sibling c1 withheld
    bad = [e for e in decision.errors if e.reason_code == "metric_label_not_in_set"]
    assert len(bad) == 1
    assert bad[0].tool_call_id == "c2"  # identity preserved for downstream replay
    assert bad[0].category == "in_catalog"
    assert bad[0].field_path == "arguments.metric_label"


def test_all_valid_labels_accept_and_preserve():
    calls = [_metric_call("d1", "ticket_price"), _metric_call("d2", "opening_hours")]
    ctx = {"metric_labels": ["ticket_price", "opening_hours"]}
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", ctx)
    assert decision.decision == "accepted"
    assert [v.arguments["metric_label"] for v in decision.validated_calls] == [
        "ticket_price",
        "opening_hours",
    ]


def test_metric_scrape_list_labels_membership_through_guard():
    """The array-label shape (metric_scrape) is membership-checked end-to-end through the guard."""
    catalog = build_tool_catalog(_raw_defs(), "metric_scrape")
    good = ToolCall(
        id="s1", name="firecrawl_scrape",
        arguments='{"id": "page-1", "metric_label": ["ticket_price", "opening_hours"]}',
    )
    ctx = {"metric_labels": ["ticket_price", "opening_hours"]}
    assert guard_proposed_calls([good], catalog, "metric_scrape", ctx).decision == "accepted"

    bad = ToolCall(
        id="s1", name="firecrawl_scrape",
        arguments='{"id": "page-1", "metric_label": ["ticket_price", "not_a_metric"]}',
    )
    decision = guard_proposed_calls([bad], catalog, "metric_scrape", ctx)
    assert decision.decision == "rejected"
    assert [e.reason_code for e in decision.errors] == ["metric_label_not_in_set"]


def test_none_validation_context_skips_membership_check():
    """With no runtime facts supplied, the data-dependent membership check is skipped."""
    calls = [_metric_call("d1", "not_in_any_set")]
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", None)
    assert decision.decision == "accepted"


def test_empty_dict_validation_context_is_supplied_data():
    """An empty dict is supplied data (not None): the empty set makes every label ineligible."""
    calls = [_metric_call("d1", "ticket_price")]
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", {})
    assert decision.decision == "rejected"
    assert decision.errors[0].reason_code == "metric_label_not_in_set"


# --------------------------------------------------------------------------------------------------
# metric_label_membership_validator — unit level, both label shapes.
# --------------------------------------------------------------------------------------------------
def test_validator_accepts_member_string():
    assert metric_label_membership_validator(
        {"metric_label": "ticket_price"}, {"metric_labels": ["ticket_price"]}
    ) == []


def test_validator_flags_each_invalid_label_in_a_list():
    issues = metric_label_membership_validator(
        {"metric_label": ["ticket_price", "bad_one", "also_bad"]},
        {"metric_labels": ["ticket_price"]},
    )
    assert len(issues) == 2  # one issue per out-of-set label
    assert all(i.field_path == "arguments.metric_label" for i in issues)
    assert all(i.reason_code == "metric_label_not_in_set" for i in issues)


# --------------------------------------------------------------------------------------------------
# Steps 3-5 (added for R3.M1.4 phase 1): rejection outcomes, replay cleanup, admitted-call prep.
# --------------------------------------------------------------------------------------------------
def _assistant_message(calls: list[ToolCall]) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in calls
        ],
    }


def test_rejection_outcomes_mark_valid_siblings_withheld():
    calls = [_metric_call("c1", "ticket_price"), _metric_call("c2", "not_a_metric")]
    ctx = {"metric_labels": ["ticket_price"]}
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", ctx)
    outcomes = build_rejection_outcomes(calls, decision)
    assert [(o.tool_call_id, o.category) for o in outcomes] == [
        ("c1", "withheld"),
        ("c2", "in_catalog"),
    ]
    assert outcomes[1].reason_codes == ("metric_label_not_in_set",)
    assert outcomes[0].raw_arguments == calls[0].arguments  # kept for attribution


def test_rejection_outcomes_empty_for_accepted_decision():
    calls = [_metric_call("c1", "ticket_price")]
    decision = guard_proposed_calls(
        calls, _metric_catalog(), "metric_web_search", {"metric_labels": ["ticket_price"]}
    )
    assert build_rejection_outcomes(calls, decision) == ()


def test_sanitize_replay_strips_out_of_catalog_call_and_keeps_the_rest():
    stray = ToolCall(id="x1", name="firecrawl_scrape", arguments="{}")
    calls = [_metric_call("c1", "ticket_price"), stray]
    decision = guard_proposed_calls(
        calls, _metric_catalog(), "metric_web_search", {"metric_labels": ["ticket_price"]}
    )
    outcomes = build_rejection_outcomes(calls, decision)
    original = _assistant_message(calls)
    sanitized = sanitize_replay_message(original, outcomes)
    assert [c["id"] for c in sanitized["tool_calls"]] == ["c1"]
    assert [c["id"] for c in original["tool_calls"]] == ["c1", "x1"]  # input not mutated


def test_sanitize_replay_returns_none_when_nothing_remains():
    stray = ToolCall(id="x1", name="firecrawl_scrape", arguments="{}")
    decision = guard_proposed_calls([stray], _metric_catalog(), "metric_web_search", None)
    outcomes = build_rejection_outcomes([stray], decision)
    assert sanitize_replay_message(_assistant_message([stray]), outcomes) is None


def test_prepare_admitted_calls_strips_metric_label_into_metadata():
    calls = [_metric_call("c1", "ticket_price")]
    decision = guard_proposed_calls(
        calls, _metric_catalog(), "metric_web_search", {"metric_labels": ["ticket_price"]}
    )
    (prepared,) = prepare_admitted_calls(decision.validated_calls, "metric_web_search")
    assert prepared.arguments == {"objective": "o", "search_queries": ["q"]}
    assert prepared.metric_labels == ("ticket_price",)
    assert "metric_label" in decision.validated_calls[0].arguments  # validated call untouched


def test_prepare_admitted_calls_passes_untagged_context_through():
    decision = guard_proposed_calls([_ok_call()], _discovery_catalog(), "website_discovery", None)
    (prepared,) = prepare_admitted_calls(decision.validated_calls, "website_discovery")
    assert prepared.metric_labels == ()
    assert prepared.arguments == decision.validated_calls[0].arguments
