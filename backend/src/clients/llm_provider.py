import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

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

        content, finish_reason = _read_first_choice(response)
        return _decode_body(
            provider=self.name,
            model=self._model,
            content=content,
            finish_reason=finish_reason,
        )

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

        content, finish_reason = _read_first_choice(response)
        return _decode_body(
            provider=self.name,
            model=self._model,
            content=content,
            finish_reason=finish_reason,
        )

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


def _read_first_choice(response: Any) -> tuple[str | None, str | None]:
    choices = getattr(response, "choices", None) or ()
    if not choices:
        return None, None
    choice = choices[0]
    return choice.message.content, choice.finish_reason


def _decode_body(
    *,
    provider: str,
    model: str,
    content: str | None,
    finish_reason: str | None,
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
