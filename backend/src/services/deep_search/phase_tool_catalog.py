"""R3.M1.1 — Phase-Scoped Tool Catalog and Call Guard.

Two reusable, LLM-agnostic abstractions a workflow caller uses in sequence when preparing a tool
turn, specified in `feature_context/R3_Specific_Metric_Resolution_spec.md` (R3.M1.1) and
exercised by `feature_context/R3_M1_1_Dry_Run_Traceflow.md`:

1. `build_tool_catalog(raw_tool_definitions, context)` — pure schema derivation. An
   application-owned `context` selects one server/tool via the policy table, a controlled copy of
   that tool's MCP input schema is derived (allowlist the server fields the model may set, inject
   the app-defined LLM-facing fields, carry any retained `$ref` with its transitive `$defs`), and
   the result is adapted to the Chat-Completions function-tool shape `call_turn` accepts. No LLM
   call, no execution, no mutation of the raw definitions. It is the one raising path of R3.M1.1:
   a missing selected server/tool, a raw schema that conflicts with expectations, or a `$ref` that
   cannot be resolved against carried `$defs` raises `MetricResolutionValidationError` before any
   tokens are spent.

2. `guard_proposed_calls(proposed_tool_calls, tool_catalog, context, validation_context)` —
   whole-message validation of the model's returned tool calls against the exact catalog offered
   for that turn, plus an optional data-dependent validator. It is all-or-nothing: a message is
   accepted only when every call passes; any error rejects the whole message and admits no sibling.
   It never raises for validation — a rejection is a normal outcome carrying per-call metadata the
   downstream replay/retry steps read, so it is returned as a `GuardDecision`.

3-5. What a caller does with the decision (added for R3.M1.4 phase 1, reusable by phase 2):
   `build_rejection_outcomes` (Step 3: one outcome per identifiable call of a rejected message,
   valid siblings marked `withheld`), `sanitize_replay_message` (Step 4: drop out-of-catalog calls
   from the assistant message before it is replayed), and `prepare_admitted_calls` (Step 5: strip
   `metric_label` before MCP execution and carry it on the prepared call).

All are module-level functions, not methods: the spec requires reuse by any tool-turn caller
(website discovery now, the metric phases later), and none holds state. R3 stage methods
(R3.M1.3 discovery, R3.M1.4 phase loop) call them; execution, history mutation, retry budgets and
tool-message construction live in those surrounding steps, not here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import uuid4

from jsonschema import Draft202012Validator

from src.clients.llm_provider import ToolCall
from src.clients.mcp_tools import RawToolDefinition, RawToolDefinitions
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import MetricResolutionValidationError

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

CATALOG_BUILT_EVENT = "r3m1_1.catalog_built"
GUARD_DECISION_EVENT = "r3m1_1.guard_decision"

# Application-owned context. MCP and the LLM never choose this; the workflow caller supplies it
# from its progress (R3.M1.3 → website_discovery; R3.M1.4 → the evidence contexts).
ToolContext = Literal["website_discovery", "metric_web_search", "site_map", "metric_scrape"]

# Error categories (spec "Rejection classification").
_CATEGORY_OUT_OF_CATALOG = "out_of_catalog"
_CATEGORY_IN_CATALOG = "in_catalog"
_CATEGORY_INVALID_STRUCTURE = "invalid_call_structure"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------------------
# Data contracts.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ValidationIssue:
    """One finding an additional validator returns; the guard stamps call metadata onto it."""

    reason_code: str
    explanation: str
    field_path: str | None = None


@dataclass(frozen=True)
class GuardError:
    """One message- or call-level validation failure, with all metadata the guard could attach."""

    reason_code: str
    explanation: str
    call_index: int | None
    tool_call_id: str | None
    tool_name: str | None
    category: str | None
    field_path: str | None


@dataclass(frozen=True)
class ValidatedCall:
    """One admitted call: its outer identity and the decoded, validated arguments object."""

    tool_call_id: str
    tool_name: str
    arguments: dict


@dataclass(frozen=True)
class GuardDecision:
    """The one message-level decision. `accepted` ⇒ errors empty and all calls in order;

    `rejected` ⇒ no call admitted and every detected error listed.
    """

    decision: Literal["accepted", "rejected"]
    validated_calls: tuple[ValidatedCall, ...]
    errors: tuple[GuardError, ...]


class AdditionalValidator(Protocol):
    """A data-dependent value check selected by tool + context, run only when prerequisites pass.

    Schemas check structure and types; a validator checks values against caller-supplied runtime
    facts (for example a label against the amenity's metric set). An empty list means success.
    """

    def __call__(
        self, arguments: dict, validation_context: Any
    ) -> list[ValidationIssue]: ...


# --------------------------------------------------------------------------------------------------
# Additional validators.
# --------------------------------------------------------------------------------------------------
def metric_label_membership_validator(
    arguments: dict, validation_context: Any
) -> list[ValidationIssue]:
    """Check each `metric_label` is in the amenity's metric set (`validation_context`).

    Handles both shapes the schema allows: a single string (metric web search) and a list of
    strings (metric scrape). An empty `metric_labels` set (an empty dict is supplied data, not
    `None`) makes every label ineligible. The schema has already guaranteed the field's presence
    and type, so this only judges membership.
    """
    allowed: set[str] = set()
    if isinstance(validation_context, dict):
        raw_allowed = validation_context.get("metric_labels")
        if isinstance(raw_allowed, (list, tuple, set)):
            allowed = {str(label) for label in raw_allowed}
    value = arguments.get("metric_label")
    if isinstance(value, str):
        candidates: list[str] = [value]
    elif isinstance(value, list):
        candidates = [str(label) for label in value]
    else:
        candidates = []
    issues: list[ValidationIssue] = []
    for label in candidates:
        if label not in allowed:
            issues.append(
                ValidationIssue(
                    reason_code="metric_label_not_in_set",
                    explanation=f"metric_label {label!r} is not in the amenity's metric set",
                    field_path="arguments.metric_label",
                )
            )
    return issues


# --------------------------------------------------------------------------------------------------
# Context policy table. One row per context: which server/tool, which server fields the model may
# set, which app-defined fields are injected, the final required list, and the validator (if any).
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Policy:
    server: str
    tool: str
    kept_fields: tuple[str, ...]
    injected_fields: tuple[tuple[str, dict], ...]
    required: tuple[str, ...]
    validator: AdditionalValidator | None


_METRIC_LABEL_STRING = {
    "type": "string",
    "description": "The exact metric label (from the amenity's metric set) this call gathers "
    "evidence for.",
}
_METRIC_LABEL_LIST = {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "description": "The metric labels (from the amenity's metric set) this page scrape gathers "
    "evidence for.",
}
_SCRAPE_CANDIDATE_ID = {
    "type": "string",
    "description": "The id of the candidate page to scrape, chosen from the mapped site's "
    "candidate list.",
}

_CONTEXT_POLICY: dict[ToolContext, _Policy] = {
    "website_discovery": _Policy(
        server="parallel",
        tool="web_search",
        kept_fields=("objective", "search_queries"),
        injected_fields=(),
        required=("objective", "search_queries"),
        validator=None,
    ),
    "metric_web_search": _Policy(
        server="parallel",
        tool="web_search",
        kept_fields=("objective", "search_queries"),
        injected_fields=(("metric_label", _METRIC_LABEL_STRING),),
        required=("objective", "search_queries", "metric_label"),
        validator=metric_label_membership_validator,
    ),
    "site_map": _Policy(
        server="firecrawl",
        tool="firecrawl_map",
        kept_fields=(),
        injected_fields=(),
        required=(),
        validator=None,
    ),
    "metric_scrape": _Policy(
        server="firecrawl",
        tool="firecrawl_scrape",
        kept_fields=(),
        injected_fields=(
            ("id", _SCRAPE_CANDIDATE_ID),
            ("metric_label", _METRIC_LABEL_LIST),
        ),
        required=("id", "metric_label"),
        validator=metric_label_membership_validator,
    ),
}


# --------------------------------------------------------------------------------------------------
# Abstraction 1 — Build LLM-Facing Tool Catalog.
# --------------------------------------------------------------------------------------------------
def build_tool_catalog(
    raw_tool_definitions: RawToolDefinitions, context: ToolContext
) -> list[dict]:
    """Derive one controlled Chat-Completions function-tool for `context`.

    Pure schema derivation; no LLM call, no execution, no mutation of `raw_tool_definitions`.
    Raises `MetricResolutionValidationError` (before any LLM call) when the selected server/tool is
    missing, the raw schema conflicts with expectations, or a retained `$ref` cannot be resolved.
    """
    catalog_build_id = uuid4().hex
    policy = _CONTEXT_POLICY.get(context)
    if policy is None:
        raise MetricResolutionValidationError(
            f"unknown tool context {context!r}", stage="build_tool_catalog"
        )
    definition = _select_definition(raw_tool_definitions, policy, context)
    parameters = _derive_controlled_schema(definition.input_schema, policy, context)
    tool = _adapt_to_function_tool(definition.name, definition.description, parameters)

    logger.info(
        json.dumps(
            {
                "event": CATALOG_BUILT_EVENT,
                "timestamp": _timestamp(),
                "catalog_build_id": catalog_build_id,
                "context": context,
                "server": policy.server,
                "tool": policy.tool,
                "exposed_fields": sorted(parameters.get("properties", {})),
                "defs_carried": len(parameters.get("$defs", {})),
            }
        )
    )
    return [tool]


def _select_definition(
    raw_tool_definitions: RawToolDefinitions, policy: _Policy, context: ToolContext
) -> RawToolDefinition:
    """Pick the server/tool the policy names; fail explicitly rather than fall back to another."""
    server_tools = raw_tool_definitions.get(policy.server)
    if not server_tools:
        raise MetricResolutionValidationError(
            f"context {context!r} selects server {policy.server!r}, which is absent from the "
            f"raw tool definitions",
            stage="build_tool_catalog",
        )
    definition = server_tools.get(policy.tool)
    if definition is None:
        raise MetricResolutionValidationError(
            f"context {context!r} selects tool {policy.tool!r} on server {policy.server!r}, "
            f"which is absent from the raw tool definitions",
            stage="build_tool_catalog",
        )
    return definition


def _derive_controlled_schema(
    input_schema: dict, policy: _Policy, context: ToolContext
) -> dict:
    """Build a restricted copy: allowlisted server fields + injected app fields, carrying $defs.

    Operates on a deep copy of `input_schema`, so the caller's raw definition is never mutated.
    """
    source = deepcopy(input_schema)
    source_props = source.get("properties")
    source_props = source_props if isinstance(source_props, dict) else {}
    source_defs = source.get("$defs")
    source_defs = source_defs if isinstance(source_defs, dict) else {}

    kept_props: dict[str, Any] = {}
    for name in policy.kept_fields:
        if name not in source_props:
            raise MetricResolutionValidationError(
                f"context {context!r} keeps field {name!r}, which is absent from the raw "
                f"{policy.tool!r} schema",
                stage="build_tool_catalog",
            )
        kept_props[name] = source_props[name]

    # search_queries is wired to the gateway's execution interface (a non-empty list of query
    # strings), so its type is checked and its minimum enforced; a conflict fails before the call.
    if "search_queries" in kept_props:
        kept_props["search_queries"] = _controlled_query_field(
            kept_props["search_queries"], policy.tool
        )

    injected_props: dict[str, Any] = {name: deepcopy(frag) for name, frag in policy.injected_fields}

    # Carry only the $defs the retained fields actually reference (transitively); fail if a ref
    # cannot be resolved. Injected fields carry no refs but are scanned for completeness.
    carried_defs = _carry_referenced_defs({**kept_props, **injected_props}, source_defs)

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {**kept_props, **injected_props},
        "required": list(policy.required),
        "additionalProperties": False,
    }
    if carried_defs:
        parameters["$defs"] = carried_defs
    return parameters


def _controlled_query_field(fragment: dict, tool: str) -> dict:
    """Return the retained `search_queries` field with the minimum-of-one enforced.

    An inline array-of-strings is type-checked and gets `minItems: 1`. A `$ref`-expressed field is
    kept as a reference (its target is resolve-checked when `$defs` are carried) with `minItems: 1`
    added as a sibling — JSON Schema 2020-12 applies siblings to `$ref`, so the minimum holds
    without inlining the definition. Any other shape conflicts with the execution interface.
    """
    if "type" in fragment:
        if not _is_array_of_strings(fragment):
            raise MetricResolutionValidationError(
                f"raw {tool!r} schema field 'search_queries' is not an array of strings; it is "
                f"incompatible with the guard and execution interface",
                stage="build_tool_catalog",
            )
        fragment["minItems"] = 1
        return fragment
    if "$ref" in fragment:
        fragment.setdefault("minItems", 1)
        return fragment
    raise MetricResolutionValidationError(
        f"raw {tool!r} schema field 'search_queries' has an unrecognised shape; it is "
        f"incompatible with the guard and execution interface",
        stage="build_tool_catalog",
    )


def _is_array_of_strings(schema: Any) -> bool:
    """True when a JSON-Schema fragment describes an array whose items are strings."""
    if not isinstance(schema, dict):
        return False
    type_value = schema.get("type")
    is_array = type_value == "array" or (isinstance(type_value, list) and "array" in type_value)
    if not is_array:
        return False
    items = schema.get("items")
    if not isinstance(items, dict):
        return False
    item_type = items.get("type")
    return item_type == "string" or (isinstance(item_type, list) and "string" in item_type)


def _carry_referenced_defs(kept: dict, source_defs: dict) -> dict:
    """Collect the `$defs` the retained fields reference, transitively, and verify each resolves.

    Only local refs of the form `#/$defs/<name>` are carried. Any other `$ref` (an external URL,
    a non-$defs pointer) cannot be safely carried, so catalog construction fails rather than emit
    a schema the model could not honor. A referenced name absent from `source_defs` also fails.
    """
    needed: set[str] = set()
    pending = list(_find_refs(kept))
    while pending:
        ref = pending.pop()
        name = _local_def_name(ref)
        if name is None:
            raise MetricResolutionValidationError(
                f"retained schema carries an unsupported $ref {ref!r}; only local #/$defs/ refs "
                f"can be preserved",
                stage="build_tool_catalog",
            )
        if name in needed:
            continue
        if name not in source_defs:
            raise MetricResolutionValidationError(
                f"retained schema references $defs/{name}, which is absent from the raw schema",
                stage="build_tool_catalog",
            )
        needed.add(name)
        pending.extend(_find_refs(source_defs[name]))
    return {name: deepcopy(source_defs[name]) for name in needed}


def _local_def_name(ref: str) -> str | None:
    """Return the `<name>` of a `#/$defs/<name>` ref, or None for any other ref form."""
    prefix = "#/$defs/"
    if ref.startswith(prefix):
        name = ref[len(prefix) :]
        # A nested pointer (e.g. #/$defs/A/properties/x) is not a plain def name we can carry.
        return name if name and "/" not in name else None
    return None


def _find_refs(node: Any) -> list[str]:
    """Collect every `$ref` string anywhere inside a schema fragment."""
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(_find_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_find_refs(item))
    return refs


def _adapt_to_function_tool(name: str, description: str | None, parameters: dict) -> dict:
    """Wrap a controlled parameter schema in the Chat-Completions function-tool shape."""
    function: dict[str, Any] = {"name": name, "parameters": parameters}
    if description is not None:
        function["description"] = description
    return {"type": "function", "function": function}


# --------------------------------------------------------------------------------------------------
# Abstraction 2 — Guard Proposed Calls.
# --------------------------------------------------------------------------------------------------
# JSON-Schema validator keyword → stable guard reason code (spec error contract).
_SCHEMA_REASON_BY_VALIDATOR: dict[str, str] = {
    "required": "missing_required_argument",
    "type": "invalid_argument_type",
    "additionalProperties": "unexpected_argument",
    "minItems": "too_few_items",
    "enum": "value_not_allowed",
}


def guard_proposed_calls(
    proposed_tool_calls: Sequence[ToolCall],
    tool_catalog: list[dict],
    context: ToolContext,
    validation_context: Any | None,
) -> GuardDecision:
    """Validate the whole tool-call message against the offered catalog; accept all or reject all.

    Collects every detectable error across all calls (skipping checks whose prerequisites failed)
    and never raises for validation. Accepts only a non-empty message whose every call passes,
    returning the calls in original order with decoded, un-normalized arguments.
    """
    guard_id = uuid4().hex
    schemas = _schema_by_tool_name(tool_catalog)
    validator = _validator_for(context)
    errors: list[GuardError] = []
    validated: list[ValidatedCall] = []
    validator_ran = False

    if not proposed_tool_calls:
        errors.append(
            GuardError(
                reason_code="no_tool_calls",
                explanation="the assistant message contained no tool calls",
                call_index=None,
                tool_call_id=None,
                tool_name=None,
                category=None,
                field_path=None,
            )
        )
        return _finish(guard_id, context, errors, validated, validator_ran)

    id_counts = _count_ids(proposed_tool_calls)

    for index, call in enumerate(proposed_tool_calls):
        tool_call_id = call.id or None
        tool_name = call.name or None

        # Step 2 — outer structure and unique IDs. A failure here is a prerequisite for every
        # later check, so the call is skipped (its args are not inspected).
        if not call.id:
            errors.append(
                _structure_error(
                    "missing_tool_call_id", "tool call is missing its id", index, None, tool_name
                )
            )
            continue
        if id_counts[call.id] > 1:
            errors.append(
                _structure_error(
                    "duplicate_tool_call_id",
                    f"tool-call id {call.id!r} is used more than once in the message",
                    index,
                    tool_call_id,
                    tool_name,
                )
            )
            continue
        if not call.name:
            errors.append(
                _structure_error(
                    "missing_tool_name", "tool call is missing its name", index, tool_call_id, None
                )
            )
            continue

        # Step 3 — exact-match catalog membership.
        if call.name not in schemas:
            errors.append(
                GuardError(
                    reason_code="out_of_catalog",
                    explanation=f"tool {call.name!r} is not in the offered catalog",
                    call_index=index,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    category=_CATEGORY_OUT_OF_CATALOG,
                    field_path=None,
                )
            )
            continue

        # Step 4 — decode the argument JSON string.
        try:
            arguments = json.loads(call.arguments)
        except (ValueError, TypeError):
            errors.append(
                _in_catalog_error(
                    "invalid_argument_json",
                    "tool-call arguments were not valid JSON",
                    index,
                    tool_call_id,
                    tool_name,
                    "arguments",
                )
            )
            continue
        if not isinstance(arguments, dict):
            errors.append(
                _in_catalog_error(
                    "invalid_argument_json",
                    "tool-call arguments did not decode to a JSON object",
                    index,
                    tool_call_id,
                    tool_name,
                    "arguments",
                )
            )
            continue

        # Step 5 — schema validation (no coercion, repair, or normalization).
        schema_errors = _schema_errors(schemas[call.name], arguments, index, tool_call_id, tool_name)
        if schema_errors:
            errors.extend(schema_errors)
            continue

        # Step 6 — data-dependent validator, only when supplied with runtime facts and selected.
        if validation_context is not None and validator is not None:
            validator_ran = True
            for issue in validator(arguments, validation_context):
                errors.append(
                    _in_catalog_error(
                        issue.reason_code,
                        issue.explanation,
                        index,
                        tool_call_id,
                        tool_name,
                        issue.field_path,
                    )
                )
            if any(e.call_index == index for e in errors):
                continue

        validated.append(
            ValidatedCall(tool_call_id=call.id, tool_name=call.name, arguments=arguments)
        )

    return _finish(guard_id, context, errors, validated, validator_ran)


def _finish(
    guard_id: str,
    context: ToolContext,
    errors: list[GuardError],
    validated: list[ValidatedCall],
    validator_ran: bool,
) -> GuardDecision:
    """Apply the all-or-nothing rule and log one decision node."""
    if errors:
        decision = GuardDecision("rejected", (), tuple(errors))
    else:
        decision = GuardDecision("accepted", tuple(validated), ())
    logger.info(
        json.dumps(
            {
                "event": GUARD_DECISION_EVENT,
                "timestamp": _timestamp(),
                "guard_id": guard_id,
                "context": context,
                "decision": decision.decision,
                "call_count": len(validated) if decision.decision == "accepted" else None,
                "error_count": len(decision.errors),
                "reason_codes": sorted({e.reason_code for e in decision.errors}),
                "validator_ran": validator_ran,
            }
        )
    )
    return decision


def _schema_by_tool_name(tool_catalog: list[dict]) -> dict[str, dict]:
    """Index each function tool's parameter schema by its name (trusts our own builder's output)."""
    indexed: dict[str, dict] = {}
    for tool in tool_catalog:
        function = tool.get("function", {})
        name = function.get("name")
        if isinstance(name, str):
            indexed[name] = function.get("parameters", {})
    return indexed


def _validator_for(context: ToolContext) -> AdditionalValidator | None:
    """Select the additional validator for a context (the policy owns the tool+context mapping)."""
    policy = _CONTEXT_POLICY.get(context)
    return policy.validator if policy is not None else None


def _schema_errors(
    schema: dict,
    arguments: dict,
    call_index: int,
    tool_call_id: str | None,
    tool_name: str | None,
) -> list[GuardError]:
    """Validate decoded arguments against the tool schema; map each failure to a GuardError."""
    errors: list[GuardError] = []
    validator = Draft202012Validator(schema)
    for error in validator.iter_errors(arguments):
        reason = _SCHEMA_REASON_BY_VALIDATOR.get(str(error.validator), "schema_validation")
        errors.append(
            _in_catalog_error(
                reason,
                error.message,
                call_index,
                tool_call_id,
                tool_name,
                _field_path(error),
            )
        )
    return errors


def _field_path(error: Any) -> str:
    """Render a jsonschema error path as `arguments[.<key>...]`."""
    parts = [str(part) for part in getattr(error, "absolute_path", [])]
    return "arguments." + ".".join(parts) if parts else "arguments"


def _count_ids(calls: Sequence[ToolCall]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in calls:
        if call.id:
            counts[call.id] = counts.get(call.id, 0) + 1
    return counts


def _structure_error(
    reason_code: str,
    explanation: str,
    call_index: int,
    tool_call_id: str | None,
    tool_name: str | None,
) -> GuardError:
    return GuardError(
        reason_code=reason_code,
        explanation=explanation,
        call_index=call_index,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        category=_CATEGORY_INVALID_STRUCTURE,
        field_path=None,
    )


def _in_catalog_error(
    reason_code: str,
    explanation: str,
    call_index: int,
    tool_call_id: str | None,
    tool_name: str | None,
    field_path: str | None,
) -> GuardError:
    return GuardError(
        reason_code=reason_code,
        explanation=explanation,
        call_index=call_index,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        category=_CATEGORY_IN_CATALOG,
        field_path=field_path,
    )


# --------------------------------------------------------------------------------------------------
# Steps 3-5 — what the caller does with a GuardDecision (reusable by every tool-turn caller).
# Pure functions: they read the decision and the proposed calls; they never execute, retry, or log.
# --------------------------------------------------------------------------------------------------
RejectedCategory = Literal["in_catalog", "out_of_catalog", "invalid_call_structure", "withheld"]

# The LLM-facing field that tags a call with the metric(s) it serves. It is stripped before MCP
# execution (the server has no such argument) and carried on the prepared call instead.
_METRIC_LABEL_FIELD = "metric_label"


@dataclass(frozen=True)
class RejectedCallOutcome:
    """Step 3: the result for one identifiable call of a rejected message.

    `category` is the call's own error category, or `withheld` for a sibling that passed every check
    but was not admitted because the message as a whole was rejected. `raw_arguments` is the model's
    argument string, unchanged, so a caller can attribute the call (for example to its metric).
    """

    tool_call_id: str
    tool_name: str | None
    category: RejectedCategory
    reason_codes: tuple[str, ...]
    raw_arguments: str


@dataclass(frozen=True)
class PreparedCall:
    """Step 5: one admitted call ready for MCP execution.

    `arguments` holds only what the MCP tool accepts (`metric_label` removed); `metric_labels` keeps
    the stripped tag(s) so the caller can attribute the result. Empty for untagged contexts.
    """

    tool_call_id: str
    tool_name: str
    arguments: dict
    metric_labels: tuple[str, ...]


def build_rejection_outcomes(
    proposed_calls: Sequence[ToolCall], decision: GuardDecision
) -> tuple[RejectedCallOutcome, ...]:
    """Step 3: one outcome per call that has a usable (present, unique) id, in message order.

    Siblings with no error of their own are `withheld`. A call without a usable id gets no outcome:
    no tool message can be paired with it, so the replay step drops it (see `sanitize_replay_message`).
    An accepted decision has no rejected calls, so it yields an empty tuple.
    """
    if decision.decision == "accepted":
        return ()
    errors_by_index: dict[int, list[GuardError]] = {}
    for error in decision.errors:
        if error.call_index is not None:
            errors_by_index.setdefault(error.call_index, []).append(error)
    id_counts = _count_ids(proposed_calls)
    outcomes: list[RejectedCallOutcome] = []
    for index, call in enumerate(proposed_calls):
        if not call.id or id_counts.get(call.id, 0) > 1:
            continue
        call_errors = errors_by_index.get(index, [])
        if call_errors:
            category: RejectedCategory = call_errors[0].category or _CATEGORY_IN_CATALOG  # type: ignore[assignment]
            reasons = tuple(dict.fromkeys(e.reason_code for e in call_errors))
        else:
            category = "withheld"
            reasons = ("message_rejected",)
        outcomes.append(
            RejectedCallOutcome(
                tool_call_id=call.id,
                tool_name=call.name or None,
                category=category,
                reason_codes=reasons,
                raw_arguments=call.arguments,
            )
        )
    return tuple(outcomes)


def sanitize_replay_message(
    assistant_message: dict, outcomes: Sequence[RejectedCallOutcome]
) -> dict | None:
    """Step 4: the assistant message to replay after a rejection, or `None` to replay nothing.

    Keeps only calls that will be answered by a tool message: in-catalog, structural-but-identified,
    and withheld calls. Out-of-catalog calls (and calls with no usable id) are removed, so the replayed
    history never names a tool the provider was not offered (Groq compatibility) and never holds an
    unanswered call. Returns `None` when no call and no content remain. The input is not mutated.
    """
    kept_ids = {o.tool_call_id for o in outcomes if o.category != _CATEGORY_OUT_OF_CATALOG}
    kept_calls = [
        call for call in assistant_message.get("tool_calls") or [] if call.get("id") in kept_ids
    ]
    content = assistant_message.get("content")
    if not kept_calls and not content:
        return None
    sanitized = {key: value for key, value in assistant_message.items() if key != "tool_calls"}
    if kept_calls:
        sanitized["tool_calls"] = kept_calls
    return sanitized


def prepare_admitted_calls(
    validated_calls: Sequence[ValidatedCall], context: ToolContext
) -> tuple[PreparedCall, ...]:
    """Step 5: strip the `metric_label` tag from each admitted call and carry it alongside.

    The tag exists only in metric contexts (the policy injects it); other contexts pass arguments
    through unchanged with no labels. The guard has already validated the tag's type, so a single
    string becomes a one-label tuple and a list keeps its order. Values are not normalized.
    """
    policy = _CONTEXT_POLICY.get(context)
    tagged = policy is not None and any(
        name == _METRIC_LABEL_FIELD for name, _ in policy.injected_fields
    )
    prepared: list[PreparedCall] = []
    for call in validated_calls:
        arguments = dict(call.arguments)
        labels: tuple[str, ...] = ()
        if tagged:
            raw = arguments.pop(_METRIC_LABEL_FIELD, None)
            if isinstance(raw, str):
                labels = (raw,)
            elif isinstance(raw, list):
                labels = tuple(str(label) for label in raw)
        prepared.append(
            PreparedCall(
                tool_call_id=call.tool_call_id,
                tool_name=call.tool_name,
                arguments=arguments,
                metric_labels=labels,
            )
        )
    return tuple(prepared)
