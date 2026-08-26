from dataclasses import dataclass
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient

from src.core.config import Settings

# Publishable-key projects sign user access tokens with asymmetric keys, not HS256.
ALLOWED_ALGORITHMS = ("ES256", "RS256")


class TokenVerificationError(Exception):
    """Raised when a JWT cannot be verified locally for this API."""


@dataclass(frozen=True)
class VerifiedAccessToken:
    """Claims taken from a locally verified access token — never a raw JWT dict."""

    algorithm: str
    audience_matched: bool
    subject: str
    email: str | None
    user_name: str | None


class AccessTokenVerifier:
    """Verify Supabase access tokens locally via JWKS (or a test signing key)."""

    def __init__(
        self,
        *,
        audience: str,
        issuer: str,
        jwks_url: str | None = None,
        signing_key: Any | None = None,
    ) -> None:
        if signing_key is None and not jwks_url:
            raise ValueError("AccessTokenVerifier requires jwks_url or signing_key")
        self._audience = audience
        self._issuer = issuer
        self._signing_key = signing_key
        self._jwks_client = PyJWKClient(jwks_url, cache_keys=True) if jwks_url else None

    def verify(self, token: str) -> VerifiedAccessToken:
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise TokenVerificationError("Token header is not a valid JWT") from exc

        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise TokenVerificationError("Token is not signed with an allowed algorithm")

        key = self._resolve_key(token)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["aud", "exp", "sub", "iss"],
                    "verify_aud": True,
                },
            )
        except InvalidTokenError as exc:
            raise TokenVerificationError("Token signature or claims are invalid") from exc

        audience = claims.get("aud")
        audience_matched = self._audience_matches(audience)
        if not audience_matched:
            raise TokenVerificationError("Token audience does not match this API")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenVerificationError("Token is missing a subject")

        return VerifiedAccessToken(
            algorithm=algorithm,
            audience_matched=True,
            subject=subject,
            email=_claim_str(claims.get("email")),
            user_name=_user_name_from_claims(claims),
        )

    def _resolve_key(self, token: str) -> Any:
        if self._signing_key is not None:
            return self._signing_key
        assert self._jwks_client is not None
        try:
            return self._jwks_client.get_signing_key_from_jwt(token).key
        except Exception as exc:
            raise TokenVerificationError("Unable to resolve the token signing key") from exc

    def _audience_matches(self, audience: object) -> bool:
        if isinstance(audience, str):
            return audience == self._audience
        if isinstance(audience, list):
            return self._audience in audience
        return False


def _claim_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _user_name_from_claims(claims: dict[str, Any]) -> str | None:
    metadata = claims.get("user_metadata")
    if not isinstance(metadata, dict):
        return None
    return _claim_str(metadata.get("full_name"))


def create_access_token_verifier(settings: Settings) -> AccessTokenVerifier:
    return AccessTokenVerifier(
        audience=settings.supabase_jwt_audience,
        issuer=settings.supabase_jwt_issuer,
        jwks_url=settings.supabase_jwks_url,
    )
