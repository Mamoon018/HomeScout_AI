"""A provider wrapper over the real OpenAI -> Groq chain that records, replays, and injects failures.

- record: forwards each call to the real providers in order and keeps the body per schema name.
- replay: returns the recorded bodies per schema name without any network call, so a second path
  sees exactly the LLM output the first path saw (parity can be compared exactly).
- fail_once: raises the provider error on the next call of a chosen schema, because a real
  provider cannot be made to fail on demand. Every other body still comes from a real provider.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence

from src.clients.llm_provider import StructuredLLMProvider
from src.exceptions.llm import LLMProviderError


class Tape:
    """Recorded real bodies, keyed by schema name, in call order."""

    def __init__(self) -> None:
        self.bodies: dict[str, list[dict]] = {}

    def add(self, schema_name: str, body: dict) -> None:
        self.bodies.setdefault(schema_name, []).append(copy.deepcopy(body))


class RecordingProvider:
    """One provider object that the R1 caller sees; it fronts the real chain or a tape."""

    name = "recording"
    model = "real-chain"

    def __init__(
        self,
        *,
        real_providers: Sequence[StructuredLLMProvider] = (),
        tape: Tape | None = None,
        mode: str = "record",
    ) -> None:
        assert mode in ("record", "replay")
        self._real = tuple(real_providers)
        self.tape = tape if tape is not None else Tape()
        self.mode = mode
        self.fail_once: set[str] = set()
        self.calls: list[str] = []
        self._cursor: dict[str, int] = {}

    def rewind(self) -> None:
        """Start replay from the first body of every schema again (used before a retry)."""
        self._cursor.clear()

    async def generate_structured(
        self, *, instruction: str, user_content: str, json_schema: dict, schema_name: str
    ) -> dict:
        self.calls.append(schema_name)
        if schema_name in self.fail_once:
            self.fail_once.discard(schema_name)
            raise LLMProviderError("injected provider failure", failure_class="availability")

        if self.mode == "replay":
            queue = self.tape.bodies.get(schema_name, [])
            index = self._cursor.get(schema_name, 0)
            if index >= len(queue):
                raise LLMProviderError(f"tape has no body {index} for {schema_name}")
            self._cursor[schema_name] = index + 1
            return copy.deepcopy(queue[index])

        last: LLMProviderError | None = None
        for provider in self._real:
            try:
                body = await provider.generate_structured(
                    instruction=instruction,
                    user_content=user_content,
                    json_schema=json_schema,
                    schema_name=schema_name,
                )
            except LLMProviderError as exc:
                last = exc
                continue
            self.tape.add(schema_name, body)
            return body
        raise last or LLMProviderError("no real provider configured")

    async def generate_turn(self, **_: object):  # pragma: no cover - R1 never calls it
        raise NotImplementedError

    async def aclose(self) -> None:
        for provider in self._real:
            await provider.aclose()
