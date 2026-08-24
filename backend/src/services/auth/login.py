from dataclasses import dataclass
from enum import Enum

from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError

from src.services.auth.access_token import AccessTokenVerifier, TokenVerificationError

MAX_FAILED_ATTEMPTS = 5
DEFAULT_ACCESS_TOKEN_MAX_AGE = 12 * 60 * 60
REFRESH_TOKEN_MAX_AGE = 60 * 60 * 24 * 30

_failed_attempts: dict[str, int] = {}


class LoginOutcome(str, Enum):
    SUCCESS = "success"
    INVALID_CREDENTIALS = "invalid_credentials"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class IssuedIdentity:
    """Fields taken from a Supabase session for cookies — never the raw SDK object."""

    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    email: str | None


@dataclass(frozen=True)
class LoginResult:
    outcome: LoginOutcome
    message: str | None = None
    error: str | None = None
    identity: IssuedIdentity | None = None


@dataclass(frozen=True)
class AccessTokenCookiePolicy:
    """Cookie attributes required for same-origin session cookies."""

    name: str = "access_token"
    httponly: bool = True
    secure: bool = True
    samesite: str = "strict"
    path: str = "/"


@dataclass(frozen=True)
class RefreshTokenCookiePolicy:
    """Refresh token is httpOnly and only attached on the refresh path."""

    name: str = "refresh_token"
    httponly: bool = True
    secure: bool = True
    samesite: str = "strict"
    path: str = "/auth/refresh"


ACCESS_TOKEN_COOKIE_POLICY = AccessTokenCookiePolicy()
REFRESH_TOKEN_COOKIE_POLICY = RefreshTokenCookiePolicy()


@dataclass(frozen=True)
class AccessTokenCookieReceipt:
    present: bool
    matches_expected: bool
    name: str


def describe_cookie_send() -> dict[str, bool | str]:
    """Describe the Set-Cookie policy that was applied, never including the token."""
    policy = ACCESS_TOKEN_COOKIE_POLICY
    return {
        "sent": True,
        "name": policy.name,
        "http_only": policy.httponly,
        "secure": policy.secure,
        "same_site": "Strict",
        "path": policy.path,
    }


def inspect_received_access_token(
    cookie_value: str | None,
    verifier: AccessTokenVerifier,
) -> AccessTokenCookieReceipt:
    """Check that a cookie arrived and verifies locally without echoing the value."""
    present = bool(cookie_value)
    matches_expected = False
    if cookie_value:
        try:
            verifier.verify(cookie_value)
            matches_expected = True
        except TokenVerificationError:
            matches_expected = False
    return AccessTokenCookieReceipt(
        present=present,
        matches_expected=matches_expected,
        name=ACCESS_TOKEN_COOKIE_POLICY.name,
    )


def reset_failed_attempts(email: str) -> None:
    _failed_attempts.pop(email.lower(), None)


def _map_supabase_session(session: object) -> IssuedIdentity | None:
    access_token = getattr(session, "access_token", None)
    refresh_token = getattr(session, "refresh_token", None)
    expires_in = getattr(session, "expires_in", None)
    user = getattr(session, "user", None)
    user_id = getattr(user, "id", None) if user is not None else None
    email = getattr(user, "email", None) if user is not None else None

    if not isinstance(access_token, str) or not access_token:
        return None
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    if not isinstance(user_id, str) or not user_id:
        return None

    max_age = expires_in if isinstance(expires_in, int) and expires_in > 0 else DEFAULT_ACCESS_TOKEN_MAX_AGE
    return IssuedIdentity(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=max_age,
        user_id=user_id,
        email=email if isinstance(email, str) else None,
    )


def authenticate(client: Client, email: str, password: str) -> LoginResult:
    normalized_email = email.lower()

    if _failed_attempts.get(normalized_email, 0) >= MAX_FAILED_ATTEMPTS:
        return LoginResult(
            outcome=LoginOutcome.RATE_LIMITED,
            error="Too many login attempts. Please try again later.",
        )

    try:
        response = client.auth.sign_in_with_password(
            {"email": normalized_email, "password": password}
        )
    except (AuthApiError, AuthError):
        _failed_attempts[normalized_email] = _failed_attempts.get(normalized_email, 0) + 1
        return LoginResult(
            outcome=LoginOutcome.INVALID_CREDENTIALS,
            error="Invalid email or password",
        )

    identity = _map_supabase_session(getattr(response, "session", None))
    if identity is None:
        _failed_attempts[normalized_email] = _failed_attempts.get(normalized_email, 0) + 1
        return LoginResult(
            outcome=LoginOutcome.INVALID_CREDENTIALS,
            error="Invalid email or password",
        )

    reset_failed_attempts(normalized_email)
    return LoginResult(
        outcome=LoginOutcome.SUCCESS,
        message="Login successful",
        identity=identity,
    )
