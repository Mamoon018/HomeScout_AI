from httpx import ASGITransport, AsyncClient
import pytest

from src.app.api.dependencies.supabase import get_access_token_verifier, get_supabase_client
from src.app.main import app
from src.services.auth.session_cookies import (
    ACCESS_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_COOKIE_POLICY,
)
from tests.conftest import (
    FakeSupabaseClient,
    TEST_REFRESH_TOKEN,
    TEST_USER_NAME,
    make_access_token_verifier,
    mint_access_token,
)

REFRESH_ENDPOINT = "/auth/refresh"
WELCOME_ENDPOINT = "/api/user_welcome"


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    refreshed_access_token = mint_access_token(subject="user-1")
    app.dependency_overrides[get_supabase_client] = lambda: FakeSupabaseClient(
        mint_access_token(subject="user-1"),
        refreshed_access_token=refreshed_access_token,
    )
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_refresh_rotated_access_token_is_accepted_by_welcome(client: AsyncClient):
    client.cookies.set(
        ACCESS_TOKEN_COOKIE_POLICY.name,
        mint_access_token(expires_in_seconds=-10),
    )
    client.cookies.set(REFRESH_TOKEN_COOKIE_POLICY.name, TEST_REFRESH_TOKEN)

    expired_response = await client.get(WELCOME_ENDPOINT)
    assert expired_response.status_code == 401
    assert expired_response.json() == {
        "error": "Not authenticated",
        "code": "token_expired",
    }

    refresh_response = await client.post(REFRESH_ENDPOINT)
    assert refresh_response.status_code == 200

    welcome_response = await client.get(WELCOME_ENDPOINT)
    assert welcome_response.status_code == 200
    assert welcome_response.json() == {"message": f"Welcome {TEST_USER_NAME}!"}
