"""Gateway-level failures for R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

Setup failures (connection/listing, missing required capabilities or invalid definition shapes)
raise this family. Definition access outside a successfully open session raises McpConnectionError
with stage="get_tool_definitions". Per-call execution failures return ToolFailure. The former
connection-time shape probe has been removed; response parsing failures are per-call failures.
"""

from typing import ClassVar


class McpGatewayError(Exception):
    """Base failure surface of the MCP tool gateway.

    Named so a caller can report which stage exited without reading a traceback. Server API keys
    live only in `McpServerConfig.api_key`; they are never placed in these messages.
    """

    stage: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage


class McpConnectionError(McpGatewayError):
    """Raised when setup cannot reach a server or definitions are unavailable for this lifecycle.

    A timeout on an in-flight tool call is NOT this: that is our side giving up on one wait, and
    the open session stays in use. This is only a genuine failure to establish or query a session.

    A missing or refused Firecrawl key surfaces here: per Firecrawl's 3.29.1 changelog the hosted
    endpoint no longer serves keyless requests and answers 401, so the session cannot open
    (`stage="open"`). Not verified against the live endpoint.
    """

    stage: ClassVar[str] = "open"


class McpToolUnavailableError(McpGatewayError):
    """Required tool/argument or valid input-schema mapping missing during capability checks."""

    stage: ClassVar[str] = "verify_capabilities"
