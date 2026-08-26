import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from supabase_auth.errors import AuthApiError

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_test_key"
os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"

from src.core.config import get_settings
from src.services.auth.access_token import AccessTokenVerifier

get_settings.cache_clear()

TEST_EMAIL = "demo@homescout.ai"
TEST_PASSWORD = "password123"
TEST_CAPTCHA_TOKEN = "test-captcha-token"
TEST_USER_NAME = "Demo User"
TEST_ACCESS_TOKEN = "test-access-token"
TEST_REFRESH_TOKEN = "test-refresh-token"
TEST_ISSUER = "https://example.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"

EC_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
EC_PUBLIC_KEY = EC_PRIVATE_KEY.public_key()

# Keep dummy aliases used by older tests that may still import these names.
TEST_DUMMY_EMAIL = TEST_EMAIL
TEST_DUMMY_PASSWORD = TEST_PASSWORD


def mint_access_token(
    *,
    audience: str = TEST_AUDIENCE,
    issuer: str = TEST_ISSUER,
    subject: str = "user-1",
    email: str | None = TEST_EMAIL,
    user_name: str | None = TEST_USER_NAME,
    expires_in_seconds: int = 3600,
    algorithm: str = "ES256",
    key=None,
    include_audience: bool = True,
    include_email: bool = True,
    include_user_name: bool = True,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iss": issuer,
        "exp": now + timedelta(seconds=expires_in_seconds),
        "iat": now,
    }
    if include_audience:
        payload["aud"] = audience
    if include_email and email is not None:
        payload["email"] = email
    if include_user_name and user_name is not None:
        payload["user_metadata"] = {"full_name": user_name}
    signing_key = key if key is not None else EC_PRIVATE_KEY
    return jwt.encode(payload, signing_key, algorithm=algorithm)


def make_access_token_verifier() -> AccessTokenVerifier:
    return AccessTokenVerifier(
        audience=TEST_AUDIENCE,
        issuer=TEST_ISSUER,
        signing_key=EC_PUBLIC_KEY,
    )


class FakeSupabaseAuth:
    def __init__(
        self,
        access_token: str,
        refresh_token: str = TEST_REFRESH_TOKEN,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token

    def sign_in_with_password(self, credentials: dict[str, str]):
        if (
            credentials.get("email") == TEST_EMAIL.lower()
            and credentials.get("password") == TEST_PASSWORD
        ):
            user = SimpleNamespace(
                id="user-1",
                email=TEST_EMAIL,
                user_metadata={"full_name": TEST_USER_NAME},
            )
            session = SimpleNamespace(
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                expires_in=3600,
                user=user,
            )
            return SimpleNamespace(session=session, user=user)
        raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")


class FakeSupabaseClient:
    def __init__(self, access_token: str) -> None:
        self.auth = FakeSupabaseAuth(access_token)
