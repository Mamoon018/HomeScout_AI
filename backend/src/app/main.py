from fastapi import FastAPI

from src.app.api.routes.auth import router as auth_router
from src.core.logging import configure_logging

configure_logging()

app = FastAPI(title="HomeScout Auth")
app.include_router(auth_router)
