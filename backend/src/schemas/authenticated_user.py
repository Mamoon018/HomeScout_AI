from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """Request-scoped identity. user_id is the canonical scoping key, never email."""

    user_id: str
    email: str
    user_name: str
