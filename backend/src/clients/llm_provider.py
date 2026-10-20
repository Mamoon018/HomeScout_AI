import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, Sequence

import groq
import openai

from src.core.config import Settings
from src.core.logging import DEEP_SEARCH_LOGGER_NAME
from src.exceptions.llm import LLMProviderError, LLMResponseTruncatedError

logger = logging.getLogger(DEEP_SEARCH_LOGGER_NAME)

OPENAI_PROVIDER_NAME = "openai"
GROQ_PROVIDER_NAME = "groq"

# Both SDKs report a body cut short by the token limit with this finish reason.
_TRUNCATED_FINISH_REASON = "length"

# A clean structured completion ends with this finish reason. Any other value (for example
# "content_filter"), apart from the truncation case handled separately, means the provider
# did not produce a usable body, so the structured funnel falls back (C3.1.2 iteration M1).
_CLEAN_FINISH_REASON = "stop"

# The shared caller's funnel emits these provider-attempt and raw-body records; the sample
# runners read them back. They live here now that the funnel is shared across R1 and R2;
# `requirement_interpretation` re-exports them so existing imports keep working.
LLM_PROVIDER_ATTEMPT_EVENT = "llm_provider.attempt"
LLM_PROVIDER_RAW_BODY_EVENT = "llm_provider.raw_body"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ToolCall:
    """One function tool call the model emitted in a turn.

    `arguments` is the raw JSON string from the model. It is not strict-validated (Groq does
    not support strict function tools), so C3.1.3 validates it in code.
    """

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AssistantTurn:
    """One assistant turn: its content, any tool calls, and the provider-neutral message.

    `message` is an OpenAI-chat-format assistant message the caller appends back to the
    history before the next turn. `tool_calls` is empty (never None) when the model answered
    with content only.
    """

    provider: str
    finish_reason: str | None
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    message: dict


class StructuredLLMProvider(Protocol):
    """One schema-constrained generation, decoded to a dict."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate_structured(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
    ) -> dict: ...

    async def generate_turn(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict,
    ) -> AssistantTurn: ...

    async def aclose(self) -> None: ...


class OpenAIStructuredProvider:
    """OpenAI chat completions constrained by a strict JSON schema."""

    def __init__(self, client: openai.AsyncOpenAI, *, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return OPENAI_PROVIDER_NAME

    @property
    def model(self) -> str:
        return self._model

    async def generate_structured(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
    ) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=_build_messages(instruction, user_content),
                response_format=_build_response_format(json_schema, schema_name),
            )
        except openai.APITimeoutError as exc:
            raise LLMProviderError("OpenAI structured call timed out") from exc
        except openai.RateLimitError as exc:
            raise LLMProviderError("OpenAI rate limited the structured call") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMProviderError("OpenAI rejected the structured call credentials") from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError("OpenAI structured call failed") from exc

        content, finish_reason, refusal = _read_first_choice(response)
        return _decode_body(
            provider=self.name,
            model=self._model,
            content=content,
            finish_reason=finish_reason,
            refusal=refusal,
        )

    async def generate_turn(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict,
    ) -> AssistantTurn:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                # A reasoning model (e.g. gpt-6-luna) rejects function tools on
                # /v1/chat/completions unless reasoning_effort is "none"; set it so the tool turn
                # is accepted. Non-reasoning models accept "none" as a no-op.
                reasoning_effort="none",
            )
        except openai.APITimeoutError as exc:
            raise LLMProviderError("OpenAI tool turn timed out") from exc
        except openai.RateLimitError as exc:
            raise LLMProviderError("OpenAI rate limited the tool turn") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMProviderError("OpenAI rejected the tool turn credentials") from exc
        except openai.OpenAIError as exc:
            raise LLMProviderError("OpenAI tool turn failed") from exc

        return _build_assistant_turn(provider=self.name, model=self._model, response=response)

    async def aclose(self) -> None:
        await self._client.close()


class GroqStructuredProvider:
    """Groq chat completions constrained by a strict JSON schema."""

    def __init__(self, client: groq.AsyncGroq, *, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return GROQ_PROVIDER_NAME

    @property
    def model(self) -> str:
        return self._model

    async def generate_structured(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
    ) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=_build_messages(instruction, user_content),
                response_format=_build_response_format(json_schema, schema_name),
            )
        except groq.APITimeoutError as exc:
            raise LLMProviderError("Groq structured call timed out") from exc
        except groq.RateLimitError as exc:
            raise LLMProviderError("Groq rate limited the structured call") from exc
        except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
            raise LLMProviderError("Groq rejected the structured call credentials") from exc
        except groq.GroqError as exc:
            raise LLMProviderError("Groq structured call failed") from exc

        content, finish_reason, refusal = _read_first_choice(response)
        return _decode_body(
            provider=self.name,
            model=self._model,
            content=content,
            finish_reason=finish_reason,
            refusal=refusal,
        )

    async def generate_turn(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict,
    ) -> AssistantTurn:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )
        except groq.APITimeoutError as exc:
            raise LLMProviderError("Groq tool turn timed out") from exc
        except groq.RateLimitError as exc:
            raise LLMProviderError("Groq rate limited the tool turn") from exc
        except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
            raise LLMProviderError("Groq rejected the tool turn credentials") from exc
        except groq.GroqError as exc:
            raise LLMProviderError("Groq tool turn failed") from exc

        return _build_assistant_turn(provider=self.name, model=self._model, response=response)

    async def aclose(self) -> None:
        await self._client.close()


def _build_messages(instruction: str, user_content: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": instruction},
        {"role": "user", "content": user_content},
    ]


def _build_response_format(json_schema: dict, schema_name: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": json_schema,
        },
    }


def _read_first_choice(response: Any) -> tuple[str | None, str | None, str | None]:
    choices = getattr(response, "choices", None) or ()
    if not choices:
        return None, None, None
    choice = choices[0]
    # `refusal` is an OpenAI field set when the model declines; Groq has no such attribute,
    # so `getattr` yields None there and the refusal check downstream is a no-op (M1, F1).
    refusal = getattr(choice.message, "refusal", None)
    return choice.message.content, choice.finish_reason, refusal


def _read_turn_choice(response: Any) -> Any | None:
    choices = getattr(response, "choices", None) or ()
    if not choices:
        return None
    return choices[0]


def _build_assistant_turn(*, provider: str, model: str, response: Any) -> AssistantTurn:
    """Map one SDK response into a provider-neutral `AssistantTurn`.

    Logs the turn boundary, rejects a truncated turn (so the funnel falls back and the
    half-built tool call is never executed), and rejects a turn with neither content nor
    tool calls as an empty provider response.
    """
    choice = _read_turn_choice(response)
    message = getattr(choice, "message", None)
    finish_reason = getattr(choice, "finish_reason", None)
    content = getattr(message, "content", None)
    raw_tool_calls = getattr(message, "tool_calls", None) or ()
    tool_calls = tuple(
        ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
        for call in raw_tool_calls
    )

    logger.info(
        json.dumps(
            {
                "event": "llm.generate_turn",
                "timestamp": _timestamp(),
                "provider": provider,
                "model": model,
                "finish_reason": finish_reason,
                "tool_call_count": len(tool_calls),
                "content_length": len(content or ""),
            }
        )
    )
    logger.debug(
        json.dumps(
            {
                "event": "llm.generate_turn.content",
                "provider": provider,
                "model": model,
                "content": content,
                "tool_calls": [
                    {"name": call.name, "arguments": call.arguments} for call in tool_calls
                ],
            }
        )
    )

    if finish_reason == _TRUNCATED_FINISH_REASON:
        raise LLMResponseTruncatedError(
            f"{provider} hit the token limit before completing the tool turn"
        )
    if not content and not tool_calls:
        raise LLMProviderError(f"{provider} returned an empty tool turn")

    appended_message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        appended_message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in tool_calls
        ]
    return AssistantTurn(
        provider=provider,
        finish_reason=finish_reason,
        content=content,
        tool_calls=tool_calls,
        message=appended_message,
    )


def _decode_body(
    *,
    provider: str,
    model: str,
    content: str | None,
    finish_reason: str | None,
    refusal: str | None = None,
) -> dict:
    logger.info(
        json.dumps(
            {
                "event": "llm.generate_structured",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": provider,
                "model": model,
                "finish_reason": finish_reason,
                "response_length": len(content or ""),
            }
        )
    )
    logger.debug(
        json.dumps(
            {
                "event": "llm.generate_structured.content",
                "provider": provider,
                "model": model,
                "content": content,
            }
        )
    )

    if finish_reason == _TRUNCATED_FINISH_REASON:
        raise LLMResponseTruncatedError(
            f"{provider} hit the token limit before completing the body"
        )
    # M1: a decline or a filtered/abnormal stop is a provider failure, so the funnel falls
    # back even when partial content would otherwise decode. Refusal is checked first because
    # a declined turn can still carry a non-`stop` finish reason.
    if refusal:
        raise LLMProviderError(f"{provider} returned a refusal instead of a body")
    if finish_reason not in (None, _CLEAN_FINISH_REASON):
        raise LLMProviderError(
            f"{provider} returned an abnormal finish_reason {finish_reason!r}"
        )
    if not content:
        raise LLMProviderError(f"{provider} returned an empty body")

    try:
        body = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"{provider} returned a body that is not valid JSON") from exc
    if not isinstance(body, dict):
        raise LLMProviderError(f"{provider} returned a JSON value that is not an object")
    return body


def create_openai_provider(settings: Settings) -> OpenAIStructuredProvider:
    """Authenticated OpenAI adapter bound to the configured extraction model."""
    try:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    except openai.OpenAIError as exc:
        raise LLMProviderError("OpenAI client could not be built; check OPENAI_API_KEY") from exc
    return OpenAIStructuredProvider(client, model=settings.openai_extraction_model)


def create_groq_provider(settings: Settings) -> GroqStructuredProvider:
    """Authenticated Groq adapter bound to the configured extraction model."""
    try:
        client = groq.AsyncGroq(api_key=settings.groq_api_key)
    except groq.GroqError as exc:
        raise LLMProviderError("Groq client could not be built; check GROQ_API_KEY") from exc
    return GroqStructuredProvider(client, model=settings.groq_extraction_model)


_PROVIDER_FACTORIES: dict[str, Callable[[Settings], StructuredLLMProvider]] = {
    OPENAI_PROVIDER_NAME: create_openai_provider,
    GROQ_PROVIDER_NAME: create_groq_provider,
}


def create_llm_providers(settings: Settings) -> tuple[StructuredLLMProvider, ...]:
    """Build the provider chain in the order LLM_PROVIDER_ORDER names them."""
    names = [name.strip().lower() for name in settings.llm_provider_order.split(",")]
    ordered = tuple(name for name in dict.fromkeys(names) if name)
    if not ordered:
        raise ValueError("LLM_PROVIDER_ORDER must name at least one provider")

    unknown = [name for name in ordered if name not in _PROVIDER_FACTORIES]
    if unknown:
        known = ", ".join(sorted(_PROVIDER_FACTORIES))
        raise ValueError(
            f"LLM_PROVIDER_ORDER names unknown providers {unknown}; known providers are {known}"
        )

    return tuple(_PROVIDER_FACTORIES[name](settings) for name in ordered)


class StructuredLLMCaller:
    """The shared OpenAI-then-Groq chain for both R1 and R2.

    It exposes the structured call (the funnel lifted out of R1's `_call_providers`) and a
    tool turn, both over the same bound provider order and the same fallback rule: fall back
    only on `LLMProviderError` (including a truncated body/turn), never for a
    returned-but-unwanted body. The service decides the `stage` and the typed error class, so
    this client layer stays free of any `services`-owned exception.
    """

    def __init__(self, providers: Sequence[StructuredLLMProvider]) -> None:
        self._providers = tuple(providers)
        self._closed = False

    @property
    def providers(self) -> tuple[StructuredLLMProvider, ...]:
        return self._providers

    async def call_structured(
        self,
        *,
        instruction: str,
        user_content: str,
        json_schema: dict,
        schema_name: str,
        stage: str,
        provider_error_cls: type[Exception],
    ) -> tuple[dict, str]:
        """Try providers in the bound order; return the first body or a typed provider error."""
        body: dict | None = None
        answered_by: str | None = None

        for provider in self._providers:
            try:
                body = await provider.generate_structured(
                    instruction=instruction,
                    user_content=user_content,
                    json_schema=json_schema,
                    schema_name=schema_name,
                )
            except LLMProviderError as exc:
                # The adapter wraps the SDK error; the SDK's own message (for example an
                # HTTP 400 naming a rejected schema path) is only on __cause__.
                detail = str(exc)
                if exc.__cause__ is not None:
                    detail = f"{detail} | cause: {type(exc.__cause__).__name__}: {exc.__cause__}"
                logger.info(
                    json.dumps(
                        {
                            "event": LLM_PROVIDER_ATTEMPT_EVENT,
                            "timestamp": _timestamp(),
                            "stage": stage,
                            "provider": provider.name,
                            "model": provider.model,
                            "outcome": "failed",
                            "detail": detail,
                        }
                    )
                )
                continue

            answered_by = provider.name
            logger.info(
                json.dumps(
                    {
                        "event": LLM_PROVIDER_ATTEMPT_EVENT,
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "provider": provider.name,
                        "model": provider.model,
                        "outcome": "answered",
                    }
                )
            )
            break

        if body is None or answered_by is None:
            logger.info(
                json.dumps(
                    {
                        "event": "llm_provider.rejected",
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "reason": "no_provider_answered",
                        "attempted": [provider.name for provider in self._providers],
                    }
                )
            )
            raise provider_error_cls(
                f"No LLM provider returned a {stage} body", stage=stage
            )

        logger.debug(
            json.dumps(
                {
                    "event": LLM_PROVIDER_RAW_BODY_EVENT,
                    "stage": stage,
                    "provider": answered_by,
                    "body": body,
                }
            )
        )
        return body, answered_by

    async def call_turn(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str | dict,
        stage: str,
        provider_error_cls: type[Exception],
    ) -> AssistantTurn:
        """Try providers in the bound order; return the first assistant turn or a typed error."""
        for provider in self._providers:
            try:
                turn = await provider.generate_turn(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                )
            except LLMProviderError as exc:
                detail = str(exc)
                if exc.__cause__ is not None:
                    detail = f"{detail} | cause: {type(exc.__cause__).__name__}: {exc.__cause__}"
                logger.info(
                    json.dumps(
                        {
                            "event": LLM_PROVIDER_ATTEMPT_EVENT,
                            "timestamp": _timestamp(),
                            "stage": stage,
                            "provider": provider.name,
                            "model": provider.model,
                            "outcome": "failed",
                            "detail": detail,
                        }
                    )
                )
                continue

            logger.info(
                json.dumps(
                    {
                        "event": LLM_PROVIDER_ATTEMPT_EVENT,
                        "timestamp": _timestamp(),
                        "stage": stage,
                        "provider": provider.name,
                        "model": provider.model,
                        "outcome": "answered",
                    }
                )
            )
            return turn

        logger.info(
            json.dumps(
                {
                    "event": "llm_provider.rejected",
                    "timestamp": _timestamp(),
                    "stage": stage,
                    "reason": "no_provider_answered",
                    "attempted": [provider.name for provider in self._providers],
                }
            )
        )
        raise provider_error_cls(
            f"No LLM provider returned a {stage} tool turn", stage=stage
        )

    async def aclose(self) -> None:
        """Close each provider's HTTP session once; safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        for provider in self._providers:
            await provider.aclose()


def create_structured_llm_caller(settings: Settings) -> StructuredLLMCaller:
    """Composition root for the shared caller: bind the chain LLM_PROVIDER_ORDER names."""
    return StructuredLLMCaller(create_llm_providers(settings))
