from pydantic import BaseModel


class TokenCheckResponse(BaseModel):
    """Diagnostic proof that the access-token cookie can be verified locally."""

    checkable: bool
    algorithm: str | None = None
    audience_matched: bool = False
