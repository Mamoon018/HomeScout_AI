"""R3.M1.1 — deterministic code-path tests for the tool catalog builder and the call guard.

No live MCP, LLM, or network: raw tool definitions are hand-built fixtures and proposed calls are
crafted `ToolCall`s, so every branch the live sample runner cannot prove deterministically is
asserted here (allowlist/injection/$defs carrying, raw immutability, the eight guard steps, the
all-or-nothing rejection, and the metric-label validator in both directions).
"""

from copy import deepcopy

import pytest

from src.clients.llm_provider import ToolCall
from src.clients.mcp_tools import RawToolDefinition
from src.exceptions.deep_search import MetricResolutionValidationError
from src.services.deep_search.phase_tool_catalog import (
    build_tool_catalog,
    guard_proposed_calls,
    metric_label_membership_validator,
)


# --------------------------------------------------------------------------------------------------
# Fixtures — hand-built raw tool definitions.
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
            # An app/extra field the allowlist must drop.
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
            "firecrawl_map": RawToolDefinition("firecrawl_map", "map a site", _firecrawl_map_schema()),
            "firecrawl_scrape": RawToolDefinition(
                "firecrawl_scrape", "scrape a page", _firecrawl_scrape_schema()
            ),
        },
    }


def _params(catalog: list[dict]) -> dict:
    return catalog[0]["function"]["parameters"]


# --------------------------------------------------------------------------------------------------
# build_tool_catalog — happy paths per context.
# --------------------------------------------------------------------------------------------------
def test_website_discovery_exposes_only_objective_and_queries():
    catalog = build_tool_catalog(_raw_defs(), "website_discovery")
    assert [t["function"]["name"] for t in catalog] == ["web_search"]
    params = _params(catalog)
    assert set(params["properties"]) == {"objective", "search_queries"}
    assert "session_id" not in params["properties"]  # app/extra field dropped
    assert "metric_label" not in params["properties"]
    assert params["required"] == ["objective", "search_queries"]
    assert params["additionalProperties"] is False
    assert params["properties"]["search_queries"]["minItems"] == 1


def test_metric_web_search_adds_required_metric_label():
    params = _params(build_tool_catalog(_raw_defs(), "metric_web_search"))
    assert set(params["properties"]) == {"objective", "search_queries", "metric_label"}
    assert params["properties"]["metric_label"]["type"] == "string"
    assert "metric_label" in params["required"]


def test_metric_scrape_drops_url_injects_id_and_label_list():
    params = _params(build_tool_catalog(_raw_defs(), "metric_scrape"))
    assert set(params["properties"]) == {"id", "metric_label"}  # url/formats dropped
    assert params["properties"]["metric_label"]["type"] == "array"
    assert set(params["required"]) == {"id", "metric_label"}
    assert params["additionalProperties"] is False


def test_site_map_has_no_llm_settable_arguments():
    params = _params(build_tool_catalog(_raw_defs(), "site_map"))
    assert params["properties"] == {}
    assert params["required"] == []


# --------------------------------------------------------------------------------------------------
# build_tool_catalog — $ref / $defs preservation and raw immutability.
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
    params = _params(build_tool_catalog(_raw_defs(_ref_web_schema()), "website_discovery"))
    assert set(params["$defs"]) == {"QueryList", "Query"}  # Unused dropped
    assert params["properties"]["search_queries"]["$ref"] == "#/$defs/QueryList"
    assert params["properties"]["search_queries"]["minItems"] == 1  # sibling minimum added


def test_raw_definitions_are_not_mutated():
    raw = _raw_defs(_ref_web_schema())
    snapshot = deepcopy(raw)
    build_tool_catalog(raw, "website_discovery")
    assert raw == snapshot


# --------------------------------------------------------------------------------------------------
# build_tool_catalog — construction failures raise before any LLM call.
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
    schema["properties"]["search_queries"] = {"type": "string"}
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


def test_unresolvable_local_ref_raises():
    schema = _web_search_schema()
    schema["properties"]["search_queries"] = {"$ref": "#/$defs/Missing"}
    # no $defs at all → the ref cannot resolve
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


def test_unsupported_external_ref_raises():
    schema = _ref_web_schema()
    schema["properties"]["search_queries"] = {"$ref": "https://example.com/schema.json"}
    with pytest.raises(MetricResolutionValidationError):
        build_tool_catalog(_raw_defs(schema), "website_discovery")


# --------------------------------------------------------------------------------------------------
# guard_proposed_calls — structure, catalog, decode, schema.
# --------------------------------------------------------------------------------------------------
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
    assert err.category is None
    assert err.call_index is None and err.field_path is None


def test_accept_preserves_order_and_decoded_arguments():
    calls = [_ok_call("c1", "first"), _ok_call("c2", "second")]
    decision = guard_proposed_calls(calls, _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "accepted"
    assert [v.tool_call_id for v in decision.validated_calls] == ["c1", "c2"]
    assert decision.validated_calls[0].arguments == {
        "objective": "first",
        "search_queries": ["a query"],
    }


def test_arguments_not_normalized():
    call = ToolCall(
        id="c1",
        name="web_search",
        arguments='{"objective": "  spaced  ", "search_queries": ["  a  ", "a"]}',
    )
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "accepted"
    # No trim, no dedup.
    assert decision.validated_calls[0].arguments["objective"] == "  spaced  "
    assert decision.validated_calls[0].arguments["search_queries"] == ["  a  ", "a"]


def test_missing_id_is_invalid_structure_and_skips_schema():
    call = ToolCall(id="", name="web_search", arguments='{"objective": "x"}')  # also schema-invalid
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert len(decision.errors) == 1  # dependent schema check skipped
    assert decision.errors[0].category == "invalid_call_structure"
    assert decision.errors[0].reason_code == "missing_tool_call_id"


def test_duplicate_ids_are_invalid_structure():
    calls = [_ok_call("dup"), _ok_call("dup")]
    decision = guard_proposed_calls(calls, _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert {e.reason_code for e in decision.errors} == {"duplicate_tool_call_id"}
    assert all(e.category == "invalid_call_structure" for e in decision.errors)


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
    call = ToolCall(id="c1", name="web_search", arguments="[1, 2]")
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.errors[0].reason_code == "invalid_argument_json"


def test_schema_failure_is_in_catalog_with_field_path():
    # missing required objective + extra field → in_catalog errors with paths
    call = ToolCall(
        id="c1", name="web_search", arguments='{"search_queries": ["q"], "nope": 1}'
    )
    decision = guard_proposed_calls([call], _discovery_catalog(), "website_discovery", None)
    assert decision.decision == "rejected"
    assert all(e.category == "in_catalog" for e in decision.errors)
    assert any(e.reason_code == "missing_required_argument" for e in decision.errors)
    assert any(e.reason_code == "unexpected_argument" for e in decision.errors)


def test_all_errors_collected_across_calls():
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
    calls = [_metric_call("c1", "ticket_price"), _metric_call("c2", "wheelchair_access")]
    ctx = {"metric_labels": ["ticket_price", "opening_hours"]}
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", ctx)
    assert decision.decision == "rejected"
    assert not decision.validated_calls  # valid sibling c1 withheld
    bad = [e for e in decision.errors if e.reason_code == "metric_label_not_in_set"]
    assert len(bad) == 1
    assert bad[0].tool_call_id == "c2"
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


def test_none_validation_context_skips_membership_check():
    calls = [_metric_call("d1", "not_in_any_set")]
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", None)
    assert decision.decision == "accepted"


def test_empty_dict_validation_context_is_supplied_data():
    calls = [_metric_call("d1", "ticket_price")]
    decision = guard_proposed_calls(calls, _metric_catalog(), "metric_web_search", {})
    assert decision.decision == "rejected"  # empty set → every label ineligible
    assert decision.errors[0].reason_code == "metric_label_not_in_set"


# --------------------------------------------------------------------------------------------------
# metric_label_membership_validator — unit-level, both label shapes.
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
    assert len(issues) == 2
    assert all(i.field_path == "arguments.metric_label" for i in issues)
