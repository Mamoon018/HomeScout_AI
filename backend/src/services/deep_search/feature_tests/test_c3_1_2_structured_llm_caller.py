"""Offline fixtures for C3.1.2: the shared StructuredLLMCaller tool turn.

No live calls. A hand-written fake provider stands in for OpenAI/Groq. The suite proves the
tool-turn funnel (fallback, truncation, exhaustion, no-fallback-on-returned-turn, tool-call
parsing, passthrough), the lifted structured funnel's regression behavior, and the
caller/feature close lifecycle.
"""

import json
import logging
from types import SimpleNamespace

import pytest

from src.clients.llm_provider import (
    LLM_PROVIDER_ATTEMPT_EVENT,
    LLM_PROVIDER_RAW_BODY_EVENT,
    AssistantTurn,
    StructuredLLMCaller,
    ToolCall,
    _build_assistant_turn,
    _decode_body,
    _read_first_choice,
)
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.deep_search import (
    CategoryMappingProviderError,
    MetricResolutionProviderError,
)
from src.exceptions.llm import LLMProviderError, LLMResponseTruncatedError

STAGE = "run_llm_metric_resolution"


# --- fakes ------------------------------------------------------------------


class FakeProvider:
    """Duck-types StructuredLLMProvider; pops queued turns/bodies or raises when told."""

    def __init__(self, name: str, *, turns=None, bodies=None) -> None:
        self.name = name
        self.model = f"{name}-model"
        self._turns = list(turns or [])
        self._bodies = list(bodies or [])
        self.turn_calls: list[dict] = []
        self.close_count = 0

    async def generate_structured(self, *, instruction, user_content, json_schema, schema_name):
        if not self._bodies:
            raise LLMProviderError(f"{self.name}: no recorded body left")
        item = self._bodies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def generate_turn(self, *, messages, tools, tool_choice):
        self.turn_calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        if not self._turns:
            raise LLMProviderError(f"{self.name}: no recorded turn left")
        item = self._turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self) -> None:
        self.close_count += 1


class _Recorder:
    """Stands in for a responsibility whose aclose the feature calls."""

    def __init__(self) -> None:
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


def _turn(provider="openai", *, content=None, tool_calls=()):
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in tool_calls
        ]
    return AssistantTurn(
        provider=provider,
        finish_reason="tool_calls" if tool_calls else "stop",
        content=content,
        tool_calls=tuple(tool_calls),
        message=message,
    )


def _sdk_response(*, content=None, tool_calls=None, finish_reason="stop", refusal=None):
    raw_calls = None
    if tool_calls is not None:
        raw_calls = [
            SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=args))
            for cid, name, args in tool_calls
        ]
    message = SimpleNamespace(content=content, tool_calls=raw_calls, refusal=refusal)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass

    def events(self, *names):
        return [r for r in self.records if r.get("event") in names]


@pytest.fixture
def collector():
    logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)
    handler = _Collector()
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


# --- tool-turn funnel -------------------------------------------------------


async def test_call_turn_falls_back_to_second_provider(collector):
    answered = _turn("groq", content="done")
    p0 = FakeProvider("openai", turns=[LLMProviderError("boom")])
    p1 = FakeProvider("groq", turns=[answered])
    caller = StructuredLLMCaller([p0, p1])

    result = await caller.call_turn(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_choice="auto",
        stage=STAGE,
        provider_error_cls=MetricResolutionProviderError,
    )

    assert result is answered
    attempts = collector.events(LLM_PROVIDER_ATTEMPT_EVENT)
    assert [(a["provider"], a["outcome"]) for a in attempts] == [
        ("openai", "failed"),
        ("groq", "answered"),
    ]


async def test_call_turn_truncation_triggers_fallback():
    answered = _turn("groq", content="done")
    p0 = FakeProvider("openai", turns=[LLMResponseTruncatedError("cut off")])
    p1 = FakeProvider("groq", turns=[answered])
    caller = StructuredLLMCaller([p0, p1])

    result = await caller.call_turn(
        messages=[], tools=[], tool_choice="auto", stage=STAGE,
        provider_error_cls=MetricResolutionProviderError,
    )
    assert result is answered


async def test_call_turn_all_truncated_raises_typed():
    p0 = FakeProvider("openai", turns=[LLMResponseTruncatedError("cut")])
    p1 = FakeProvider("groq", turns=[LLMResponseTruncatedError("cut")])
    caller = StructuredLLMCaller([p0, p1])

    with pytest.raises(MetricResolutionProviderError) as exc:
        await caller.call_turn(
            messages=[], tools=[], tool_choice="auto", stage=STAGE,
            provider_error_cls=MetricResolutionProviderError,
        )
    assert exc.value.stage == STAGE


async def test_call_turn_exhaustion_raises_with_stage(collector):
    p0 = FakeProvider("openai", turns=[LLMProviderError("a")])
    p1 = FakeProvider("groq", turns=[LLMProviderError("b")])
    caller = StructuredLLMCaller([p0, p1])

    with pytest.raises(MetricResolutionProviderError) as exc:
        await caller.call_turn(
            messages=[], tools=[], tool_choice="auto", stage=STAGE,
            provider_error_cls=MetricResolutionProviderError,
        )
    assert exc.value.stage == STAGE
    assert collector.events("llm_provider.rejected")


async def test_call_turn_returns_without_trying_next():
    answered = _turn("openai", content="final", tool_calls=())
    p0 = FakeProvider("openai", turns=[answered])
    p1 = FakeProvider("groq", turns=[_turn("groq", content="unused")])
    caller = StructuredLLMCaller([p0, p1])

    result = await caller.call_turn(
        messages=[], tools=[], tool_choice="auto", stage=STAGE,
        provider_error_cls=MetricResolutionProviderError,
    )
    assert result is answered
    assert p1.turn_calls == []  # second provider never consulted


async def test_call_turn_passes_tools_and_tool_choice():
    tools = [{"type": "function", "function": {"name": "web_search"}}]
    p0 = FakeProvider("openai", turns=[_turn("openai", content="ok")])
    caller = StructuredLLMCaller([p0])

    await caller.call_turn(
        messages=[{"role": "user", "content": "q"}],
        tools=tools,
        tool_choice="required",
        stage=STAGE,
        provider_error_cls=MetricResolutionProviderError,
    )
    assert p0.turn_calls[0]["tools"] == tools
    assert p0.turn_calls[0]["tool_choice"] == "required"


# --- _build_assistant_turn --------------------------------------------------


def test_build_turn_parses_multiple_tool_calls():
    response = _sdk_response(
        content=None,
        tool_calls=[
            ("call_1", "web_search", '{"objective":"x"}'),
            ("call_2", "firecrawl_crawl", '{"url":"https://e.com"}'),
        ],
        finish_reason="tool_calls",
    )
    turn = _build_assistant_turn(provider="openai", model="m", response=response)

    assert turn.tool_calls == (
        ToolCall(id="call_1", name="web_search", arguments='{"objective":"x"}'),
        ToolCall(id="call_2", name="firecrawl_crawl", arguments='{"url":"https://e.com"}'),
    )
    assert turn.message["role"] == "assistant"
    assert [tc["id"] for tc in turn.message["tool_calls"]] == ["call_1", "call_2"]
    assert turn.message["tool_calls"][0]["function"]["name"] == "web_search"


def test_build_turn_content_only_has_no_tool_calls_key():
    turn = _build_assistant_turn(
        provider="openai", model="m", response=_sdk_response(content="hello", finish_reason="stop")
    )
    assert turn.tool_calls == ()
    assert turn.content == "hello"
    assert "tool_calls" not in turn.message


def test_build_turn_truncated_raises():
    response = _sdk_response(content="part", finish_reason="length")
    with pytest.raises(LLMResponseTruncatedError):
        _build_assistant_turn(provider="openai", model="m", response=response)


def test_build_turn_empty_raises():
    response = _sdk_response(content=None, tool_calls=None, finish_reason="stop")
    with pytest.raises(LLMProviderError):
        _build_assistant_turn(provider="openai", model="m", response=response)


# --- lifted structured funnel (regression) ----------------------------------


async def test_call_structured_falls_back_and_returns_body(collector):
    p0 = FakeProvider("openai", bodies=[LLMProviderError("boom")])
    p1 = FakeProvider("groq", bodies=[{"ok": 1}])
    caller = StructuredLLMCaller([p0, p1])

    body, answered_by = await caller.call_structured(
        instruction="i", user_content="u", json_schema={}, schema_name="s",
        stage="execute_taxonomy_mapping", provider_error_cls=CategoryMappingProviderError,
    )
    assert body == {"ok": 1}
    assert answered_by == "groq"
    assert collector.events(LLM_PROVIDER_RAW_BODY_EVENT)
    outcomes = [a["outcome"] for a in collector.events(LLM_PROVIDER_ATTEMPT_EVENT)]
    assert outcomes == ["failed", "answered"]


async def test_call_structured_exhaustion_raises_with_stage():
    p0 = FakeProvider("openai", bodies=[LLMProviderError("a")])
    caller = StructuredLLMCaller([p0])

    with pytest.raises(CategoryMappingProviderError) as exc:
        await caller.call_structured(
            instruction="i", user_content="u", json_schema={}, schema_name="s",
            stage="execute_taxonomy_mapping", provider_error_cls=CategoryMappingProviderError,
        )
    assert exc.value.stage == "execute_taxonomy_mapping"


async def test_call_structured_does_not_fall_back_on_returned_body():
    p0 = FakeProvider("openai", bodies=[{"unexpected": True}])
    p1 = FakeProvider("groq", bodies=[{"never": True}])
    caller = StructuredLLMCaller([p0, p1])

    body, answered_by = await caller.call_structured(
        instruction="i", user_content="u", json_schema={}, schema_name="s",
        stage="execute_taxonomy_mapping", provider_error_cls=CategoryMappingProviderError,
    )
    assert body == {"unexpected": True}
    assert answered_by == "openai"
    assert p1._bodies == [{"never": True}]  # untouched


# --- M1: structured-path refusal / finish_reason fallback -------------------


def test_decode_body_rejects_refusal():
    # A decline carries decodable content; the refusal, not the body, drives the rejection.
    with pytest.raises(LLMProviderError):
        _decode_body(
            provider="openai",
            model="m",
            content='{"ok": 1}',
            finish_reason="stop",
            refusal="I can't help with that.",
        )


def test_decode_body_rejects_content_filter():
    with pytest.raises(LLMProviderError):
        _decode_body(
            provider="openai",
            model="m",
            content='{"ok": 1}',
            finish_reason="content_filter",
        )


def test_decode_body_accepts_clean_stop_no_over_reach():
    # Same decodable content as the rejection cases; a clean stop with no refusal succeeds,
    # proving the check is refusal/finish_reason-driven, not content-driven.
    body = _decode_body(
        provider="openai",
        model="m",
        content='{"ok": 1}',
        finish_reason="stop",
        refusal=None,
    )
    assert body == {"ok": 1}


def test_read_first_choice_surfaces_refusal():
    response = _sdk_response(content='{"ok": 1}', finish_reason="stop", refusal="declined")
    content, finish_reason, refusal = _read_first_choice(response)
    assert content == '{"ok": 1}'
    assert finish_reason == "stop"
    assert refusal == "declined"


class _DecodingProvider:
    """Routes a queued SDK response through the real _read_first_choice + _decode_body,
    so a refusal / abnormal finish_reason becomes an LLMProviderError the way a real adapter would.
    """

    def __init__(self, name, *, responses):
        self.name = name
        self.model = f"{name}-model"
        self._responses = list(responses)
        self.close_count = 0

    async def generate_structured(self, *, instruction, user_content, json_schema, schema_name):
        response = self._responses.pop(0)
        content, finish_reason, refusal = _read_first_choice(response)
        return _decode_body(
            provider=self.name, model=self.model,
            content=content, finish_reason=finish_reason, refusal=refusal,
        )

    async def aclose(self):
        self.close_count += 1


async def test_call_structured_falls_back_on_refusal_then_answers():
    p0 = _DecodingProvider("openai", responses=[
        _sdk_response(content='{"ok": 0}', finish_reason="stop", refusal="declined"),
    ])
    p1 = _DecodingProvider("groq", responses=[
        _sdk_response(content='{"ok": 1}', finish_reason="stop"),
    ])
    caller = StructuredLLMCaller([p0, p1])

    body, answered_by = await caller.call_structured(
        instruction="i", user_content="u", json_schema={}, schema_name="s",
        stage=STAGE, provider_error_cls=MetricResolutionProviderError,
    )
    assert body == {"ok": 1}
    assert answered_by == "groq"


async def test_call_structured_all_refuse_raises_typed():
    p0 = _DecodingProvider("openai", responses=[
        _sdk_response(content='{"ok": 0}', finish_reason="stop", refusal="declined"),
    ])
    p1 = _DecodingProvider("groq", responses=[
        _sdk_response(content='{"ok": 0}', finish_reason="content_filter"),
    ])
    caller = StructuredLLMCaller([p0, p1])

    with pytest.raises(MetricResolutionProviderError) as exc:
        await caller.call_structured(
            instruction="i", user_content="u", json_schema={}, schema_name="s",
            stage=STAGE, provider_error_cls=MetricResolutionProviderError,
        )
    assert exc.value.stage == STAGE


# --- lifecycle --------------------------------------------------------------


async def test_aclose_is_idempotent():
    p0 = FakeProvider("openai")
    p1 = FakeProvider("groq")
    caller = StructuredLLMCaller([p0, p1])

    await caller.aclose()
    await caller.aclose()

    assert p0.close_count == 1
    assert p1.close_count == 1


async def test_feature_closes_shared_caller_exactly_once():
    from src.services.deep_search.deep_search import DeepSearch

    provider = FakeProvider("openai")
    caller = StructuredLLMCaller([provider])
    interpretation = _Recorder()
    amenity_search = _Recorder()
    feature = DeepSearch(
        interpretation=interpretation,  # type: ignore[arg-type]
        amenity_search=amenity_search,  # type: ignore[arg-type]
        llm_caller=caller,
    )

    await feature.aclose()

    assert interpretation.close_count == 1
    assert amenity_search.close_count == 1
    assert provider.close_count == 1


async def test_injected_caller_not_closed_by_responsibility():
    from src.services.deep_search.requirement_interpretation import (
        UserRequirementsInterpretation,
    )

    provider = FakeProvider("openai")
    caller = StructuredLLMCaller([provider])

    owned = UserRequirementsInterpretation(caller)  # owns_caller default True
    await owned.aclose()
    assert provider.close_count == 1

    provider2 = FakeProvider("openai")
    caller2 = StructuredLLMCaller([provider2])
    not_owned = UserRequirementsInterpretation(caller2, owns_caller=False)
    await not_owned.aclose()
    assert provider2.close_count == 0  # feature owns it, not R1
