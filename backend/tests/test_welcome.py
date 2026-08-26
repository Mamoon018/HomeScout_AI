from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
import pytest

from src.app.api.dependencies.supabase import get_access_token_verifier, get_supabase_client
from src.app.main import app
from src.services.auth.login import ACCESS_TOKEN_COOKIE_POLICY, reset_failed_attempts
from src.services.welcome.message import get_welcome_message
from tests.conftest import (
    FakeSupabaseClient,
    TEST_ACCESS_TOKEN,
    TEST_CAPTCHA_TOKEN,
    TEST_EMAIL,
    TEST_PASSWORD,
    TEST_USER_NAME,
    make_access_token_verifier,
    mint_access_token,
)

WELCOME_ENDPOINT = "/api/user_welcome"
LOGIN_ENDPOINT = "/api/auth/login"
UNAUTHENTICATED = {"error": "Not authenticated"}


@pytest.fixture(autouse=True)
def clear_overrides():
    reset_failed_attempts(TEST_EMAIL)
    yield
    reset_failed_attempts(TEST_EMAIL)
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    app.dependency_overrides[get_supabase_client] = lambda: FakeSupabaseClient(
        TEST_ACCESS_TOKEN
    )
    app.dependency_overrides[get_access_token_verifier] = make_access_token_verifier
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac


def _set_access_cookie(client: AsyncClient, token: str) -> None:
    client.cookies.set(ACCESS_TOKEN_COOKIE_POLICY.name, token)


def test_welcome_message_requires_user_id_and_uses_user_name():
    message = get_welcome_message(user_id="user-1", user_name=TEST_USER_NAME)
    assert message == "Welcome Demo User!"
    assert "user-1" not in message
    assert TEST_EMAIL not in message

    with pytest.raises(ValueError, match="user_id"):
        get_welcome_message(user_id="", user_name=TEST_USER_NAME)


@pytest.mark.asyncio
async def test_welcome_without_cookie_returns_401(client: AsyncClient):
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_malformed_token_returns_401(client: AsyncClient):
    _set_access_cookie(client, "not-a-jwt")
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_expired_token_returns_401(client: AsyncClient):
    _set_access_cookie(client, mint_access_token(expires_in_seconds=-10))
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_bad_signature_returns_401(client: AsyncClient):
    other_key = ec.generate_private_key(ec.SECP256R1())
    _set_access_cookie(client, mint_access_token(key=other_key))
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_wrong_audience_returns_401(client: AsyncClient):
    _set_access_cookie(client, mint_access_token(audience="someone-else"))
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_missing_email_claim_returns_401(client: AsyncClient):
    _set_access_cookie(client, mint_access_token(include_email=False))
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_missing_user_name_claim_returns_401(client: AsyncClient):
    _set_access_cookie(client, mint_access_token(include_user_name=False))
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_welcome_valid_token_returns_message_for_token_subject(
    client: AsyncClient,
):
    _set_access_cookie(
        client,
        mint_access_token(subject="user-1", user_name=TEST_USER_NAME),
    )
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome Demo User!"}

    _set_access_cookie(
        client,
        mint_access_token(
            subject="user-2",
            email="other@homescout.ai",
            user_name="Other User",
        ),
    )
    response = await client.get(WELCOME_ENDPOINT)
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome Other User!"}


@pytest.mark.asyncio
async def test_login_succeeds_without_access_token_cookie(client: AsyncClient):
    response = await client.post(
        LOGIN_ENDPOINT,
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "captcha_token": TEST_CAPTCHA_TOKEN,
        },
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"
