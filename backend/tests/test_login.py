import pytest
from httpx import ASGITransport, AsyncClient

from src.app.api.dependencies.supabase import get_supabase_client
from src.app.main import app
from src.core.config import get_settings
from src.services.auth.login import (
    ACCESS_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_COOKIE_POLICY,
    CAPTCHA_REQUIRED_MESSAGE,
    MAX_FAILED_ATTEMPTS,
    authenticate,
    reset_failed_attempts,
)
from tests.conftest import (
    FakeSupabaseClient,
    TEST_ACCESS_TOKEN,
    TEST_CAPTCHA_TOKEN,
    TEST_EMAIL,
    TEST_PASSWORD,
    TEST_USER_NAME,
)

LOGIN_ENDPOINT = "/api/auth/login"
LOGIN_PAYLOAD = {
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "captcha_token": TEST_CAPTCHA_TOKEN,
}


@pytest.fixture(autouse=True)
def clear_failed_attempts():
    reset_failed_attempts(TEST_EMAIL)
    yield
    reset_failed_attempts(TEST_EMAIL)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def supabase_client() -> FakeSupabaseClient:
    return FakeSupabaseClient(TEST_ACCESS_TOKEN)


@pytest.fixture
async def client(supabase_client: FakeSupabaseClient):
    app.dependency_overrides[get_supabase_client] = lambda: supabase_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def test_authenticate_success(supabase_client: FakeSupabaseClient):
    result = authenticate(
        supabase_client,
        TEST_EMAIL,
        TEST_PASSWORD,
        TEST_CAPTCHA_TOKEN,
        captcha_required=True,
    )
    assert result.outcome.value == "success"
    assert result.message == "Login successful"
    assert result.identity is not None
    assert result.identity.access_token == TEST_ACCESS_TOKEN
    assert result.identity.refresh_token == "test-refresh-token"
    assert result.identity.expires_in == 3600
    assert result.identity.user_id == "user-1"
    assert result.identity.email == TEST_EMAIL
    assert result.identity.user_name == TEST_USER_NAME


def test_authenticate_invalid_credentials(supabase_client: FakeSupabaseClient):
    result = authenticate(
        supabase_client,
        TEST_EMAIL,
        "wrong-password",
        TEST_CAPTCHA_TOKEN,
        captcha_required=True,
    )
    assert result.outcome.value == "invalid_credentials"
    assert result.error == "Invalid email or password"
    assert result.identity is None


def test_authenticate_requires_captcha_token_when_enabled(
    supabase_client: FakeSupabaseClient,
):
    result = authenticate(
        supabase_client,
        TEST_EMAIL,
        TEST_PASSWORD,
        None,
        captcha_required=True,
    )
    assert result.outcome.value == "invalid_credentials"
    assert result.error == CAPTCHA_REQUIRED_MESSAGE


def test_authenticate_succeeds_without_captcha_token_when_disabled(
    supabase_client: FakeSupabaseClient,
):
    result = authenticate(
        supabase_client,
        TEST_EMAIL,
        TEST_PASSWORD,
        None,
        captcha_required=False,
    )
    assert result.outcome.value == "success"


@pytest.mark.asyncio
async def test_login_route_succeeds_without_captcha_when_disabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CAPTCHA_ENABLED", "false")
    get_settings.cache_clear()

    response = await client.post(
        LOGIN_ENDPOINT,
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_login_route_requires_captcha_when_enabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CAPTCHA_ENABLED", "true")
    get_settings.cache_clear()

    response = await client.post(
        LOGIN_ENDPOINT,
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 401
    assert response.json() == {"error": CAPTCHA_REQUIRED_MESSAGE}


def test_cookie_policies_use_strict_secure_httponly():
    assert ACCESS_TOKEN_COOKIE_POLICY.samesite == "strict"
    assert ACCESS_TOKEN_COOKIE_POLICY.httponly is True
    assert ACCESS_TOKEN_COOKIE_POLICY.secure is True
    assert REFRESH_TOKEN_COOKIE_POLICY.path == "/auth/refresh"
    assert REFRESH_TOKEN_COOKIE_POLICY.httponly is True
    assert REFRESH_TOKEN_COOKIE_POLICY.secure is True


def _set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def _cookie_header_for(headers: list[str], name: str) -> str:
    prefix = f"{name}="
    for header in headers:
        if header.lower().startswith(prefix):
            return header.lower()
    raise AssertionError(f"missing {name} cookie")


@pytest.mark.asyncio
async def test_login_route_success_sets_access_and_refresh_cookies(client: AsyncClient):
    response = await client.post(
        LOGIN_ENDPOINT,
        json=LOGIN_PAYLOAD,
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Login successful",
        "user_id": "user-1",
        "user_name": TEST_USER_NAME,
    }
    headers = _set_cookie_headers(response)
    access = _cookie_header_for(headers, "access_token")
    refresh = _cookie_header_for(headers, "refresh_token")
    assert "httponly" in access
    assert "secure" in access
    assert "samesite=strict" in access
    assert "path=/" in access
    assert "max-age=3600" in access
    assert "httponly" in refresh
    assert "secure" in refresh
    assert "samesite=strict" in refresh
    assert "path=/auth/refresh" in refresh
    assert TEST_ACCESS_TOKEN.lower() in access
    assert "test-refresh-token" in refresh


@pytest.mark.asyncio
async def test_login_route_invalid_credentials_does_not_set_cookie(
    client: AsyncClient,
):
    response = await client.post(
        LOGIN_ENDPOINT,
        json={**LOGIN_PAYLOAD, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"error": "Invalid email or password"}
    assert "set-cookie" not in {key.lower() for key in response.headers.keys()}


@pytest.mark.asyncio
async def test_login_route_rate_limit(client: AsyncClient):
    for _ in range(MAX_FAILED_ATTEMPTS):
        await client.post(
            LOGIN_ENDPOINT,
            json={**LOGIN_PAYLOAD, "password": "wrong-password"},
        )

    response = await client.post(
        LOGIN_ENDPOINT,
        json=LOGIN_PAYLOAD,
    )
    assert response.status_code == 429
    assert response.json() == {
        "error": "Too many login attempts. Please try again later.",
    }
