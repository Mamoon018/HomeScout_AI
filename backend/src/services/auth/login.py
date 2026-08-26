from dataclasses import dataclass
from enum import Enum

from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError

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
    """Fields taken from a Supabase session for cookies and the login body."""

    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    email: str | None
    user_name: str | None


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


def reset_failed_attempts(email: str) -> None:
    _failed_attempts.pop(email.lower(), None)


def _as_metadata_dict(value: object) -> dict | None:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else None
    return None


def _extract_user_name(user: object) -> str | None:
    for attr in ("user_metadata", "raw_user_meta_data"):
        metadata = _as_metadata_dict(getattr(user, attr, None))
        if metadata is None:
            continue
        full_name = metadata.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            return full_name
    return None


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
        user_name=_extract_user_name(user) if user is not None else None,
    )


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
