from dataclasses import dataclass
from enum import Enum

from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError

from src.services.auth.session_cookies import (
    IssuedIdentity,
    map_supabase_session,
)

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
    identity: IssuedIdentity | None = None


def reset_failed_attempts(email: str) -> None:
    _failed_attempts.pop(email.lower(), None)


def _auth_error_code(error: AuthApiError | AuthError) -> str | None:
    code = getattr(error, "code", None)
    return code if isinstance(code, str) else None


CAPTCHA_REQUIRED_MESSAGE = "Please complete the captcha challenge and try again."


def authenticate(
    client: Client,
    email: str,
    password: str,
    captcha_token: str | None,
    *,
    captcha_required: bool,
) -> LoginResult:
    normalized_email = email.lower()

    if _failed_attempts.get(normalized_email, 0) >= MAX_FAILED_ATTEMPTS:
        return LoginResult(
            outcome=LoginOutcome.RATE_LIMITED,
            error="Too many login attempts. Please try again later.",
        )

    if captcha_required and (not captcha_token or not captcha_token.strip()):
        return LoginResult(
            outcome=LoginOutcome.INVALID_CREDENTIALS,
            error=CAPTCHA_REQUIRED_MESSAGE,
        )

    sign_in_payload: dict[str, object] = {
        "email": normalized_email,
        "password": password,
    }
    if captcha_required:
        sign_in_payload["options"] = {"captcha_token": captcha_token}

    try:
        response = client.auth.sign_in_with_password(sign_in_payload)
    except (AuthApiError, AuthError) as error:
        if _auth_error_code(error) == "captcha_failed":
            return LoginResult(
                outcome=LoginOutcome.INVALID_CREDENTIALS,
                error=CAPTCHA_REQUIRED_MESSAGE,
            )

        _failed_attempts[normalized_email] = _failed_attempts.get(normalized_email, 0) + 1
        return LoginResult(
            outcome=LoginOutcome.INVALID_CREDENTIALS,
            error="Invalid email or password",
        )

    identity = map_supabase_session(getattr(response, "session", None))
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
