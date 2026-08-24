from dataclasses import dataclass
from enum import Enum

from src.core.config import get_settings

MAX_FAILED_ATTEMPTS = 5

_failed_attempts: dict[str, int] = {}


class LoginOutcome(str, Enum):
    SUCCESS = "success"
    INVALID_CREDENTIALS = "invalid_credentials"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class LoginResult:
    outcome: LoginOutcome
    message: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class AccessTokenCookiePolicy:
    """Cookie attributes required for same-origin session cookies."""

    name: str = "access_token"
    httponly: bool = True
    secure: bool = True
    samesite: str = "strict"
    path: str = "/"


ACCESS_TOKEN_COOKIE_POLICY = AccessTokenCookiePolicy()


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


def inspect_received_access_token(cookie_value: str | None) -> AccessTokenCookieReceipt:
    """Check that a cookie arrived and matches the server secret without echoing the value."""
    present = bool(cookie_value)
    matches_expected = present and cookie_value == get_settings().access_token
    return AccessTokenCookieReceipt(
        present=present,
        matches_expected=matches_expected,
        name=ACCESS_TOKEN_COOKIE_POLICY.name,
    )


def reset_failed_attempts(email: str) -> None:
    _failed_attempts.pop(email.lower(), None)


def authenticate(email: str, password: str) -> LoginResult:
    normalized_email = email.lower()

    if _failed_attempts.get(normalized_email, 0) >= MAX_FAILED_ATTEMPTS:
        return LoginResult(
            outcome=LoginOutcome.RATE_LIMITED,
            error="Too many login attempts. Please try again later.",
        )

    settings = get_settings()
    if (
        normalized_email == settings.dummy_email.lower()
        and password == settings.dummy_password
    ):
        reset_failed_attempts(normalized_email)
        return LoginResult(
            outcome=LoginOutcome.SUCCESS,
            message="Login successful",
        )

    _failed_attempts[normalized_email] = _failed_attempts.get(normalized_email, 0) + 1
    return LoginResult(
        outcome=LoginOutcome.INVALID_CREDENTIALS,
        error="Invalid email or password",
    )
