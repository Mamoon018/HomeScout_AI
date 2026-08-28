import logging
from dataclasses import dataclass

from fastapi import Response

logger = logging.getLogger("homescout.auth")

DEFAULT_ACCESS_TOKEN_MAX_AGE = 12 * 60 * 60
REFRESH_TOKEN_MAX_AGE = 60 * 60 * 24 * 30


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


def map_supabase_session(session: object) -> IssuedIdentity | None:
    """Extract cookie and identity fields from a Supabase session object."""
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


def apply_session_cookies(response: Response, identity: IssuedIdentity) -> None:
    """Set rotated access and refresh HttpOnly cookies on a response."""
    access = ACCESS_TOKEN_COOKIE_POLICY
    refresh = REFRESH_TOKEN_COOKIE_POLICY
    # Keep the access cookie in the browser for the session window even after the JWT
    # inside expires, so protected routes can return code=token_expired and trigger refresh.
    access_cookie_max_age = REFRESH_TOKEN_MAX_AGE
    response.set_cookie(
        key=access.name,
        value=identity.access_token,
        httponly=access.httponly,
        secure=access.secure,
        samesite=access.samesite,
        path=access.path,
        max_age=access_cookie_max_age,
    )
    response.set_cookie(
        key=refresh.name,
        value=identity.refresh_token,
        httponly=refresh.httponly,
        secure=refresh.secure,
        samesite=refresh.samesite,
        path=refresh.path,
        max_age=REFRESH_TOKEN_MAX_AGE,
    )
    logger.info(
        "session cookies sent access_name=%s refresh_name=%s jwt_expires_in=%s "
        "access_cookie_max_age=%s refresh_max_age=%s http_only=%s secure=%s same_site=%s "
        "access_path=%s refresh_path=%s",
        access.name,
        refresh.name,
        identity.expires_in,
        access_cookie_max_age,
        REFRESH_TOKEN_MAX_AGE,
        access.httponly,
        access.secure,
        access.samesite,
        access.path,
        refresh.path,
    )


def clear_session_cookies(response: Response) -> None:
    """Expire both session cookies so the browser drops stale tokens."""
    access = ACCESS_TOKEN_COOKIE_POLICY
    refresh = REFRESH_TOKEN_COOKIE_POLICY
    response.set_cookie(
        key=access.name,
        value="",
        httponly=access.httponly,
        secure=access.secure,
        samesite=access.samesite,
        path=access.path,
        max_age=0,
    )
    response.set_cookie(
        key=refresh.name,
        value="",
        httponly=refresh.httponly,
        secure=refresh.secure,
        samesite=refresh.samesite,
        path=refresh.path,
        max_age=0,
    )
    logger.info("session cookies cleared")
