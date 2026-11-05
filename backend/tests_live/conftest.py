"""Live suite for R1 over HTTP (spec C6). Real LLM providers, the dev Supabase project.

Kept apart from `tests/` because `tests/conftest.py` overwrites SUPABASE_URL at import time.
Settings come from backend/.env and the environment. A missing setting skips the suite with its
name; it never fails it. Never point these settings at production.

Extra settings this suite reads:
    SUPABASE_SERVICE_ROLE_KEY   service-role key of the dev project
    SUPABASE_DB_URL             direct Postgres URL of the dev project (migration test only)
    R1_TEST_USER_ID_A / _B      UUIDs of two dedicated users in the dev project's auth.users
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from src.clients.llm_provider import StructuredLLMCaller, create_llm_providers  # noqa: E402
from src.clients.supabase import create_supabase_db_client  # noqa: E402
from src.core.config import Settings, get_settings  # noqa: E402
from src.services.auth.access_token import AccessTokenVerifier  # noqa: E402
from src.services.deep_search.requirement_interpretation import (  # noqa: E402
    UserRequirementsInterpretation,
)
from tests_live.recording_provider import RecordingProvider, Tape  # noqa: E402

TEST_ISSUER = "https://live-tests.homescout.local/auth/v1"
TEST_AUDIENCE = "authenticated"
_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())

# Category names that are vague on purpose, so a real extraction usually flags them.
PAUSE_REQUIREMENTS = (
    "My partner and I are moving with our two young children and an elderly cat. We both work "
    "from home most days and walk everywhere because we sold the car last year. We need a "
    "primary school within a short walk, a supermarket for the weekly shop that is not a "
    "corner store, and something for the kids at the weekend that keeps them busy. We would "
    "also like a place to recharge after long working weeks, nothing too fancy. The cat needs "
    "regular visits for his kidney condition, so care for him nearby really matters to us. We "
    "cook most nights, enjoy quiet evenings, and would rather avoid streets with loud bars or "
    "late night traffic. Good pavements and safe crossings for the children matter a lot."
)
# Every category named plainly, so a real extraction usually raises no category flag.
NO_PAUSE_REQUIREMENTS = (
    "I am a nurse who works rotating night shifts at the city hospital and I am moving alone "
    "into a one bedroom flat. I need a gym that opens very early or stays open late, a "
    "pharmacy within walking distance, and a supermarket that is open until at least ten in "
    "the evening. I cycle to work most days, so secure bike parking near home helps. I sleep "
    "during the day, so I would prefer a quiet residential street away from schools and busy "
    "roads. I enjoy swimming on my days off and I read a lot, so a public library nearby "
    "would be welcome. I do not own a car and rarely take taxis, and I cook simple meals."
)


class LiveSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_db_url: str | None = Field(default=None, validation_alias="SUPABASE_DB_URL")
    user_a: str | None = Field(default=None, validation_alias="R1_TEST_USER_ID_A")
    user_b: str | None = Field(default=None, validation_alias="R1_TEST_USER_ID_B")


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    try:
        loaded = Settings()
    except ValidationError as exc:
        # Name the missing settings only; the error text would echo .env values.
        missing = sorted({str(error["loc"][0]) for error in exc.errors()})
        pytest.skip(f"live settings missing: {', '.join(missing)}")
    if not loaded.supabase_service_role_key:
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY is not set")
    return loaded


@pytest.fixture(scope="session")
def live() -> LiveSettings:
    return LiveSettings()


@pytest.fixture(scope="session")
def users(live: LiveSettings) -> tuple[str, str]:
    if not live.user_a:
        pytest.skip("R1_TEST_USER_ID_A is not set")
    if not live.user_b:
        pytest.skip("R1_TEST_USER_ID_B is not set")
    return live.user_a, live.user_b


def _record(settings: Settings, raw_input: str) -> tuple[Tape, dict | None, str]:
    """One real one-call run (scripted terminal answers: option 1). Returns the tape and state."""
    from unittest import mock

    from src.services.deep_search.r1_run_store import dump_state

    async def run() -> tuple[Tape, dict, str]:
        provider = RecordingProvider(real_providers=create_llm_providers(settings))
        r1 = UserRequirementsInterpretation(StructuredLLMCaller([provider]))
        prompts: list[str] = []

        def scripted(prompt: str = "") -> str:
            prompts.append(prompt)
            return "1"

        try:
            with mock.patch("builtins.input", scripted):
                state = await r1.interpret(raw_input)
        finally:
            await provider.aclose()
        return provider.tape, dump_state(state), "paused" if prompts else "finished"

    return asyncio.run(run())


@pytest.fixture(scope="session")
def pause_tape(settings: Settings):
    """Real responses for a run that paused once. Recorded once per session."""
    tape, state, path = _record(settings, PAUSE_REQUIREMENTS)
    if path != "paused":
        pytest.skip("the live extraction raised no category flag for the pause input")
    return tape, state


@pytest.fixture(scope="session")
def no_pause_tape(settings: Settings):
    tape, state, path = _record(settings, NO_PAUSE_REQUIREMENTS)
    if path != "finished":
        pytest.skip("the live extraction raised a category flag for the no-pause input")
    return tape, state


def replay_interpretation(tape: Tape) -> tuple[UserRequirementsInterpretation, RecordingProvider]:
    provider = RecordingProvider(tape=tape, mode="replay")
    return UserRequirementsInterpretation(StructuredLLMCaller([provider])), provider


@pytest.fixture
async def db_client(settings: Settings, users: tuple[str, str]):
    """Service-role async client; deletes every row of both test users afterwards."""
    client = await create_supabase_db_client(settings)
    try:
        yield client
    finally:
        for user_id in users:
            await client.table("r1_runs").delete().eq("user_id", user_id).execute()
        await client.postgrest.aclose()


def make_verifier() -> AccessTokenVerifier:
    return AccessTokenVerifier(
        audience=TEST_AUDIENCE, issuer=TEST_ISSUER, signing_key=_SIGNING_KEY.public_key()
    )


def mint_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "exp": now + timedelta(hours=1),
            "iat": now,
            "email": "r1-live@homescout.test",
            "user_metadata": {"full_name": "R1 Live Test"},
        },
        _SIGNING_KEY,
        algorithm="ES256",
    )
