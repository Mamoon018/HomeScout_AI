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

    # R2 Mechanism 3 C3.1.1 — MCP tool gateway (Parallel web_search, Firecrawl crawl).
    # Keys are optional: a keyless Parallel works at a lower anonymous limit, and a keyless
    # Firecrawl is detected by the gateway's capability check (its crawl tool is absent). Leaving
    # both unset keeps every existing M1 run and test working, since the gateway opens nothing at
    # construction time.
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

    @property
    def supabase_jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_jwt_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()

















