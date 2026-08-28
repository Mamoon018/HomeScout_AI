import pytest
from httpx import ASGITransport, AsyncClient

from src.app.api.dependencies.supabase import get_supabase_client
from src.app.main import app
from src.services.auth.session_cookies import (
    ACCESS_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_COOKIE_POLICY,
)
from tests.conftest import (
    FakeSupabaseClient,
    TEST_ACCESS_TOKEN,
    TEST_REFRESH_TOKEN,
)

REFRESH_ENDPOINT = "/auth/refresh"
UNAUTHENTICATED = {"error": "Not authenticated"}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    app.dependency_overrides[get_supabase_client] = lambda: FakeSupabaseClient(
        TEST_ACCESS_TOKEN
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def _set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def _cookie_header_for(headers: list[str], name: str) -> str:
    prefix = f"{name}="
    for header in headers:
        if header.lower().startswith(prefix):
            return header.lower()
    raise AssertionError(f"missing {name} cookie")


@pytest.mark.asyncio
async def test_refresh_success_sets_rotated_cookies(client: AsyncClient, auth_caplog):
    client.cookies.set(REFRESH_TOKEN_COOKIE_POLICY.name, TEST_REFRESH_TOKEN)

    response = await client.post(REFRESH_ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {"message": "Session refreshed"}
    assert any(
        "refresh succeeded user_id=user-1 expires_in=3600" in record.message
        for record in auth_caplog.records
    )
    assert any(
        "session cookies sent" in record.message
        and "jwt_expires_in=3600" in record.message
        and "access_cookie_max_age=2592000" in record.message
        for record in auth_caplog.records
    )

    headers = _set_cookie_headers(response)
    access = _cookie_header_for(headers, ACCESS_TOKEN_COOKIE_POLICY.name)
    refresh = _cookie_header_for(headers, REFRESH_TOKEN_COOKIE_POLICY.name)
    assert ACCESS_TOKEN_COOKIE_POLICY.name in access
    assert "rotated-refresh-token" in refresh
    assert "path=/" in access
    assert "path=/auth/refresh" in refresh


@pytest.mark.asyncio
async def test_refresh_missing_cookie_returns_401_and_clears_cookies(
    client: AsyncClient,
    auth_caplog,
):
    response = await client.post(REFRESH_ENDPOINT)

    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED
    assert any(
        "refresh rejected reason=missing_token" in record.message
        for record in auth_caplog.records
    )

    headers = _set_cookie_headers(response)
    access = _cookie_header_for(headers, ACCESS_TOKEN_COOKIE_POLICY.name)
    refresh = _cookie_header_for(headers, REFRESH_TOKEN_COOKIE_POLICY.name)
    assert "max-age=0" in access
    assert "max-age=0" in refresh


@pytest.mark.asyncio
async def test_refresh_invalid_token_returns_401_and_clears_cookies(
    client: AsyncClient,
    auth_caplog,
):
    client.cookies.set(REFRESH_TOKEN_COOKIE_POLICY.name, "invalid-refresh-token")

    response = await client.post(REFRESH_ENDPOINT)

    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED
    assert any(
        "refresh rejected reason=invalid_token" in record.message
        for record in auth_caplog.records
    )

    headers = _set_cookie_headers(response)
    access = _cookie_header_for(headers, ACCESS_TOKEN_COOKIE_POLICY.name)
    refresh = _cookie_header_for(headers, REFRESH_TOKEN_COOKIE_POLICY.name)
    assert "max-age=0" in access
    assert "max-age=0" in refresh
