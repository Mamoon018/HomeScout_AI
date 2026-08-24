from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.app.api.routes.auth import router as auth_router
from src.clients.supabase import create_supabase_client
from src.core.config import get_settings
from src.core.logging import configure_logging
from src.services.auth.access_token import create_access_token_verifier

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.supabase = create_supabase_client(settings)
    app.state.access_token_verifier = create_access_token_verifier(settings)
    yield


app = FastAPI(title="HomeScout Auth", lifespan=lifespan)
app.include_router(auth_router)
