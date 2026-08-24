import pytest
from httpx import ASGITransport, AsyncClient

from src.app.main import app
from src.core.config import get_settings
from src.services.auth.login import (
    ACCESS_TOKEN_COOKIE_POLICY,
    MAX_FAILED_ATTEMPTS,
    authenticate,
    describe_cookie_send,
    inspect_received_access_token,
    reset_failed_attempts,
)
from tests.conftest import TEST_DUMMY_EMAIL, TEST_DUMMY_PASSWORD

LOGIN_ENDPOINT = "/api/auth/login"
SESSION_ENDPOINT = "/api/auth/session"
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
    get_settings.cache_clear()
    reset_failed_attempts(TEST_DUMMY_EMAIL)
    yield
    reset_failed_attempts(TEST_DUMMY_EMAIL)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def test_authenticate_success():
    result = authenticate(TEST_DUMMY_EMAIL, TEST_DUMMY_PASSWORD)
    assert result.outcome.value == "success"
    assert result.message == "Login successful"


def test_authenticate_invalid_credentials():
    result = authenticate(TEST_DUMMY_EMAIL, "wrong-password")
    assert result.outcome.value == "invalid_credentials"
    assert result.error == "Invalid email or password"


def test_describe_cookie_send_uses_strict_secure_httponly():
    assert describe_cookie_send() == EXPECTED_COOKIE_SEND
    assert ACCESS_TOKEN_COOKIE_POLICY.samesite == "strict"
    assert ACCESS_TOKEN_COOKIE_POLICY.httponly is True
    assert ACCESS_TOKEN_COOKIE_POLICY.secure is True


def test_inspect_received_access_token_missing():
    receipt = inspect_received_access_token(None)
    assert receipt.present is False
    assert receipt.matches_expected is False
    assert receipt.name == "access_token"


def test_inspect_received_access_token_matches_secret():
    receipt = inspect_received_access_token(get_settings().access_token)
    assert receipt.present is True
    assert receipt.matches_expected is True


def test_inspect_received_access_token_rejects_wrong_value():
    receipt = inspect_received_access_token("not-the-server-secret")
    assert receipt.present is True
    assert receipt.matches_expected is False


@pytest.mark.asyncio
async def test_login_route_success_sets_cookie(client: AsyncClient):
    response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_DUMMY_EMAIL, "password": TEST_DUMMY_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Login successful",
        "cookie": EXPECTED_COOKIE_SEND,
    }
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "access_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie


@pytest.mark.asyncio
async def test_login_route_invalid_credentials_does_not_set_cookie(
    client: AsyncClient,
):
    response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_DUMMY_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"error": "Invalid email or password"}
    assert "set-cookie" not in {key.lower() for key in response.headers.keys()}


@pytest.mark.asyncio
async def test_login_route_rate_limit(client: AsyncClient):
    for _ in range(MAX_FAILED_ATTEMPTS):
        await client.post(
            LOGIN_ENDPOINT,
            json={"email": TEST_DUMMY_EMAIL, "password": "wrong-password"},
        )

    response = await client.post(
        LOGIN_ENDPOINT,
        json={"email": TEST_DUMMY_EMAIL, "password": TEST_DUMMY_PASSWORD},
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
        json={"email": TEST_DUMMY_EMAIL, "password": TEST_DUMMY_PASSWORD},
    )
    assert login_response.status_code == 200

    response = await client.get(SESSION_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {
        "present": True,
        "matches_expected": True,
        "name": "access_token",
    }
