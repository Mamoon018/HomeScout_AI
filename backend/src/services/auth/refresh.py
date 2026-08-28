import logging
from dataclasses import dataclass
from enum import Enum

from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError

from src.services.auth.session_cookies import IssuedIdentity, map_supabase_session

logger = logging.getLogger("homescout.auth")


class RefreshOutcome(str, Enum):
    SUCCESS = "success"
    MISSING_TOKEN = "missing_token"
    INVALID_TOKEN = "invalid_token"


@dataclass(frozen=True)
class RefreshResult:
    outcome: RefreshOutcome
    identity: IssuedIdentity | None = None
    error: str | None = None


def refresh_session(client: Client, refresh_token: str | None) -> RefreshResult:
    """Exchange a refresh token for a new Supabase session."""
    if not refresh_token or not refresh_token.strip():
        logger.info("refresh rejected reason=missing_token")
        return RefreshResult(
            outcome=RefreshOutcome.MISSING_TOKEN,
            error="Not authenticated",
        )

    try:
        response = client.auth.refresh_session(refresh_token)
    except (AuthApiError, AuthError):
        logger.info("refresh rejected reason=invalid_token")
        return RefreshResult(
            outcome=RefreshOutcome.INVALID_TOKEN,
            error="Not authenticated",
        )

    identity = map_supabase_session(getattr(response, "session", None))
    if identity is None:
        logger.info("refresh rejected reason=invalid_session")
        return RefreshResult(
            outcome=RefreshOutcome.INVALID_TOKEN,
            error="Not authenticated",
        )

    logger.info(
        "refresh succeeded user_id=%s expires_in=%s",
        identity.user_id,
        identity.expires_in,
    )
    return RefreshResult(outcome=RefreshOutcome.SUCCESS, identity=identity)
