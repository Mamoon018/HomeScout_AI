from fastapi import Request
from supabase import Client

from src.clients.supabase import create_supabase_client
from src.core.config import get_settings


def get_supabase_client(request: Request) -> Client:
    """Reuse the client created at startup; create once if lifespan has not run."""
    client = getattr(request.app.state, "supabase", None)
    if client is None:
        client = create_supabase_client(get_settings())
        request.app.state.supabase = client
    return client
