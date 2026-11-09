from supabase import AsyncClient, Client, acreate_client, create_client
from supabase.lib.client_options import AsyncClientOptions, SyncClientOptions

from src.core.config import Settings


def create_supabase_client(settings: Settings) -> Client:
    """One process-wide Auth client. Do not persist or auto-refresh sessions on it."""
    return create_client(
        settings.supabase_url,
        settings.supabase_publishable_key,
        options=SyncClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


async def create_supabase_db_client(settings: Settings) -> AsyncClient:
    """One process-wide async database client on the service-role key (r1_runs only).

    Async so database calls never block the event loop during long R1 requests. The
    postgrest timeout bounds every call. The caller must have checked that the key is set.
    """
    assert settings.supabase_service_role_key is not None
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=AsyncClientOptions(
            auto_refresh_token=False,
            persist_session=False,
            postgrest_client_timeout=settings.supabase_db_timeout_seconds,
        ),
    )
