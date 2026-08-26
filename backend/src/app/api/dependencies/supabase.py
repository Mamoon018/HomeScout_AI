from fastapi import Request
from supabase import Client

from src.clients.supabase import create_supabase_client
from src.core.config import get_settings
from src.services.auth.access_token import AccessTokenVerifier, create_access_token_verifier


def get_supabase_client(request: Request) -> Client:
    """Reuse the client created at startup; create once if lifespan has not run."""
    client = getattr(request.app.state, "supabase", None)
    if client is None:
        client = create_supabase_client(get_settings())
        request.app.state.supabase = client
    return client


def get_access_token_verifier(request: Request) -> AccessTokenVerifier:
    """Reuse the verifier created at startup; create once if lifespan has not run."""
    verifier = getattr(request.app.state, "access_token_verifier", None)
    if verifier is None:
        verifier = create_access_token_verifier(get_settings())
        request.app.state.access_token_verifier = verifier
    return verifier
