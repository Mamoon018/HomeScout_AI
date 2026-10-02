"""Gateway-level failures for R2 Mechanism 3 Component C3.1.1 (MCP tool gateway).

Only two conditions raise out of the gateway: it cannot connect a server session, and a required
tool or argument is missing at connect. Everything a single tool call can do wrong degrades to a
returned `ToolFailure` (see `clients.mcp_tools`) so one failed call never aborts a gather. Each
exception carries the `stage` it exited from, matching the stage convention used across
`exceptions.deep_search`.
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
    """

    stage: ClassVar[str] = "open"


class McpToolUnavailableError(McpGatewayError):
    """Raised when a required tool, or a required argument of one, is absent from a server catalog.

    A keyless Firecrawl lacks the crawl tool, so this also surfaces a missing key at connect time.
    """

    stage: ClassVar[str] = "verify_capabilities"
