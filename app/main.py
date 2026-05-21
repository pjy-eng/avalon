from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.http import router as http_router
from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Avalon Online v2", version="0.1.0")
    app.state.settings = settings or load_settings()
    app.include_router(http_router)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    return app


app = create_app()
