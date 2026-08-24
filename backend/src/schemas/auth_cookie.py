from pydantic import BaseModel


class CookieSendStatus(BaseModel):
    """Confirms the backend attached Set-Cookie without exposing the token value."""

    sent: bool
    name: str
    http_only: bool
    secure: bool
    same_site: str
    path: str


class CookieReceiveStatus(BaseModel):
    """Reports whether the browser actually sent the access-token cookie back."""

    present: bool
    matches_expected: bool
    name: str
