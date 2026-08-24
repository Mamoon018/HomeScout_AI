import pytest
from httpx import ASGITransport, AsyncClient

from src.app.api.dependencies.supabase import get_access_token_verifier, get_supabase_client
from src.app.main import app
from src.services.auth.login import (
    ACCESS_TOKEN_COOKIE_POLICY,
    REFRESH_TOKEN_COOKIE_POLICY,
    MAX_FAILED_ATTEMPTS,
    authenticate,
    describe_cookie_send,
    inspect_received_access_token,
    reset_failed_attempts,
)
from tests.conftest import (
    FakeSupabaseClient,
    TEST_EMAIL,
    TEST_PASSWORD,
    mint_access_token,
    make_access_token_verifier,
)

LOGIN_ENDPOINT = "/api/auth/login"
SESSION_ENDPOINT = "/api/auth/session"
TOKEN_CHECK_ENDPOINT = "/api/auth/token-check"
EXPECTED_COOKIE_SEND = {
    "sent": True,
    "name": "access_token",
    "http_only": True,
    "secure": True,
    "same_site": "Strict",
    "path": "/",
}


@pytest.fixture(autouse=True)
def clear_failed_attempts():
    reset_failed_attempts(TEST_EMAIL)
    yield
    reset_failed_attempts(TEST_EMAIL)
    app.dependency_overrides.clear()


@pytest.fixture
def access_token() -> str:
    return mint_access_token()


@pytest.fixture
def supabase_client(access_token: str) -> FakeSupabaseClient:
    return FakeSupabaseClient(access_token)


@pytest.fixture
def verifier():
    return make_access_token_verifier()


@pytest.fixture
async def client(supabase_client: FakeSupabaseClient, verifier):
    app.dependency_overrides[get_supabase_client] = lambda: supabase_client
    app.dependency_overrides[get_access_token_verifier] = lambda: verifier
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def test_authenticate_success(supabase_client: FakeSupabaseClient, access_token: str):
    result = authenticate(supabase_client, TEST_EMAIL, TEST_PASSWORD)
    assert result.outcome.value == "success"
    assert result.message == "Login successful"
    assert result.identity is not None
    assert result.identity.access_token == access_token
    assert result.identity.refresh_token == "test-refresh-token"
    assert result.identity.expires_in == 3600
    assert result.identity.user_id == "user-1"
    assert result.identity.email == TEST_EMAIL


def test_authenticate_invalid_credentials(supabase_client: FakeSupabaseClient):
    result = authenticate(supabase_client, TEST_EMAIL, "wrong-password")
    assert result.outcome.value == "invalid_credentials"
    assert result.error == "Invalid email or password"
    assert result.identity is None


def test_describe_cookie_send_uses_strict_secure_httponly():
    assert describe_cookie_send() == EXPECTED_COOKIE_SEND
    assert ACCESS_TOKEN_COOKIE_POLICY.samesite == "strict"
    assert ACCESS_TOKEN_COOKIE_POLICY.httponly is True
    assert ACCESS_TOKEN_COOKIE_POLICY.secure is True
    assert REFRESH_TOKEN_COOKIE_POLICY.path == "/auth/refresh"
    assert REFRESH_TOKEN_COOKIE_POLICY.httponly is True
    assert REFRESH_TOKEN_COOKIE_POLICY.secure is True


def test_inspect_received_access_token_missing(verifier):
    receipt = inspect_received_access_token(None, verifier)
    assert receipt.present is False
    assert receipt.matches_expected is False
    assert receipt.name == "access_token"


def test_inspect_received_access_token_verifies_jwt(verifier, access_token: str):
    receipt = inspect_received_access_token(access_token, verifier)
    assert receipt.present is True
    assert receipt.matches_expected is True


def test_inspect_received_access_token_rejects_wrong_value(verifier):
    receipt = inspect_received_access_token("not-a-jwt", verifier)
    assert receipt.present is True
    assert receipt.matches_expected is False


def _set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def _cookie_header_for(headers: list[str], name: str) -> str:
    prefix = f"{name}="
    for header in headers:
        if header.lower().startswith(prefix):
            return header.lower()
    raise AssertionError(f"missing {name} cookie")


@pytest.mark.asyncio
async def test_login_route_success_sets_access_and_refresh_cookies(
    client: AsyncClient, access_token: str
):
    response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Login successful",
        "cookie": EXPECTED_COOKIE_SEND,
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
    assert access_token.lower() in access
    assert "test-refresh-token" in refresh


@pytest.mark.asyncio
async def test_login_route_invalid_credentials_does_not_set_cookie(
    client: AsyncClient,
):
    response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"error": "Invalid email or password"}
    assert "set-cookie" not in {key.lower() for key in response.headers.keys()}


@pytest.mark.asyncio
async def test_login_route_rate_limit(client: AsyncClient):
    for _ in range(MAX_FAILED_ATTEMPTS):
        await client.post(
            LOGIN_ENDPOINT,
            json={"email": TEST_EMAIL, "password": "wrong-password"},
        )

    response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 429
    assert response.json() == {
        "error": "Too many login attempts. Please try again later.",
    }


@pytest.mark.asyncio
async def test_session_route_reports_missing_cookie(client: AsyncClient):
    response = await client.get(SESSION_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {
        "present": False,
        "matches_expected": False,
        "name": "access_token",
    }


@pytest.mark.asyncio
async def test_session_route_reports_cookie_after_login(client: AsyncClient):
    login_response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    response = await client.get(SESSION_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {
        "present": True,
        "matches_expected": True,
        "name": "access_token",
    }


@pytest.mark.asyncio
async def test_token_check_reports_uncheckable_when_missing(client: AsyncClient):
    response = await client.get(TOKEN_CHECK_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {
        "checkable": False,
        "algorithm": None,
        "audience_matched": False,
    }


@pytest.mark.asyncio
async def test_token_check_verifies_issued_jwt_locally(client: AsyncClient):
    login_response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    response = await client.get(TOKEN_CHECK_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {
        "checkable": True,
        "algorithm": "ES256",
        "audience_matched": True,
    }
