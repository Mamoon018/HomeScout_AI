from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Server-only settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = Field(validation_alias="SUPABASE_URL")
    supabase_publishable_key: str = Field(validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_jwt_audience: str = Field(
        default="authenticated",
        validation_alias="SUPABASE_JWT_AUDIENCE",
    )
    # Server-only key for the r1_runs table (RLS blocks every other key). Optional so auth-only
    # setups and the existing tests start without it; the R1 run endpoints answer 503 when unset.
    supabase_service_role_key: str | None = Field(
        default=None,
        validation_alias="SUPABASE_SERVICE_ROLE_KEY",
    )
    # Upper bound on one r1_runs database call, so a slow database cannot hold a request open.
    supabase_db_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        validation_alias="SUPABASE_DB_TIMEOUT_SECONDS",
    )
    # A run still `running` after this long was cut off (crash, restart) and is reported as
    # failed, not retryable. A full R1 request makes at most 7 LLM calls, well inside 3 minutes.
    r1_stale_after_seconds: float = Field(
        default=180.0,
        gt=0,
        validation_alias="R1_STALE_AFTER_SECONDS",
    )
    google_maps_api: str = Field(validation_alias="GOOGLE_MAPS_API")
    captcha_enabled: bool = Field(default=True, validation_alias="CAPTCHA_ENABLED")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    openai_api_key: str = Field(validation_alias="OPENAI_API_KEY")
    openai_extraction_model: str = Field(
        default="gpt-4o-2024-08-06",
        validation_alias="OPENAI_EXTRACTION_MODEL",
    )
    groq_api_key: str = Field(validation_alias="GROQ_API_KEY")
    groq_extraction_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias="GROQ_EXTRACTION_MODEL",
    )
    # Comma-separated provider names; the first entry is the primary.
    llm_provider_order: str = Field(
        default="openai,groq",
        validation_alias="LLM_PROVIDER_ORDER",
    )

    # R2 Mechanism 3 C3.1.1 — MCP tool gateway (Parallel web_search, Firecrawl map and scrape).
    # Keys are optional in Settings: a keyless Parallel works at a lower anonymous limit. Firecrawl
    # needs a key to run M3: per its 3.29.1 changelog the hosted endpoint no longer serves keyless
    # requests (401), so without one the gateway cannot open the session and open() raises
    # McpConnectionError. Not verified against the live endpoint. Leaving both unset keeps every
    # existing M1 run and test working, since the gateway opens nothing at construction time.
    parallel_api_key: str | None = Field(
        default=None,
        validation_alias="PARALLEL_API_KEY",
    )
    firecrawl_api_key: str | None = Field(
        default=None,
        validation_alias="FIRECRAWL_API_KEY",
    )
    parallel_mcp_url: str = Field(
        default="https://search.parallel.ai/mcp",
        validation_alias="PARALLEL_MCP_URL",
    )
    firecrawl_mcp_url: str = Field(
        default="https://mcp.firecrawl.dev/v2/mcp",
        validation_alias="FIRECRAWL_MCP_URL",
    )
    # The page the gateway maps and scrapes once at open() to confirm Firecrawl returns the MCP
    # server 3.x JSON output shape. No amenity URL exists yet at that point, so this is a fixed,
    # stable page.
    firecrawl_probe_url: str = Field(
        default="https://example.com",
        validation_alias="FIRECRAWL_PROBE_URL",
    )
    # R3.M1.5 run-level circuit breaker: consecutive `availability` LLM failures (no success in
    # between) that open the breaker for the rest of the run.
    metric_resolution_breaker_threshold: int = Field(
        default=3,
        ge=1,
        validation_alias="METRIC_RESOLUTION_BREAKER_THRESHOLD",
    )

    @property
    def supabase_jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_jwt_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()

















