import os
import sys
from pathlib import Path
from types import SimpleNamespace

from supabase_auth.errors import AuthApiError

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_test_key"

from src.core.config import get_settings

get_settings.cache_clear()

TEST_EMAIL = "demo@homescout.ai"
TEST_PASSWORD = "password123"
TEST_CAPTCHA_TOKEN = "test-captcha-token"
TEST_USER_NAME = "Demo User"
TEST_ACCESS_TOKEN = "test-access-token"
TEST_REFRESH_TOKEN = "test-refresh-token"

# Keep dummy aliases used by older tests that may still import these names.
TEST_DUMMY_EMAIL = TEST_EMAIL
TEST_DUMMY_PASSWORD = TEST_PASSWORD


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
