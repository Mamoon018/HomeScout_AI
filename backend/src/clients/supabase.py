from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

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
