"""Gateway-level failures for R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

Only three conditions raise out of the gateway: it cannot connect a server session, a required
tool or argument is missing at connect, and the Firecrawl output shape cannot be confirmed by the
connect-time probe. Everything a single tool call can do wrong later degrades to a returned
`ToolFailure` (see `clients.mcp_tools`) so one failed call never aborts a gather. Each exception
carries the `stage` it exited from (`open`, `verify_capabilities`, `verify_probe`), matching the
stage convention used across `exceptions.deep_search`.
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
    """Raised when a server session cannot be started, or a capability read cannot reach it.

    A timeout on an in-flight tool call is NOT this: that is our side giving up on one wait, and
    the open session stays in use. This is only a genuine failure to establish or query a session.

    A missing or refused Firecrawl key surfaces here: per Firecrawl's 3.29.1 changelog the hosted
    endpoint no longer serves keyless requests and answers 401, so the session cannot open
    (`stage="open"`). Not verified against the live endpoint.
    """

    stage: ClassVar[str] = "open"


class McpToolUnavailableError(McpGatewayError):
    """Raised when a required tool or argument is absent, or the output is not MCP server 3.x JSON.

    The first case uses `stage="verify_capabilities"`; a probe whose map or scrape body is not the
    expected shape (for example the plain text returned by MCP server 1.x or 2.x) uses
    `stage="verify_probe"`. A missing Firecrawl key is not reported here: the session cannot open
    at all, which is `McpConnectionError`.
    """

    stage: ClassVar[str] = "verify_capabilities"
