from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Server-only auth settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dummy_email: str = Field(validation_alias="DUMMY_EMAIL")
    dummy_password: str = Field(validation_alias="DUMMY_PASSWORD")
    access_token: str = Field(validation_alias="ACCESS_TOKEN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
