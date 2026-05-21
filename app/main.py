from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.http import router as http_router
from app.api.ws import router as ws_router
from app.application.commands import CommandGateway
from app.application.rooms import RoomService
from app.application.sessions import RoomSessionService
from app.config import Settings, load_settings
from app.infrastructure.voice import LiveKitVoiceProvider, NoopVoiceProvider
from app.paths import STATIC_DIR
from app.realtime import ConnectionManager


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Avalon Online v2", version="0.1.0")
    app_settings = settings or load_settings()
    app.state.settings = app_settings
    session_service = RoomSessionService(secret=app_settings.session_secret)
    room_service = RoomService(session_service=session_service)
    app.state.session_service = session_service
    app.state.room_service = room_service
    app.state.command_gateway = CommandGateway(room_service, session_service)
    app.state.connection_manager = ConnectionManager()
    if app_settings.voice_status == "configured":
        app.state.voice_provider = LiveKitVoiceProvider(
            app_settings.livekit_url or "",
            app_settings.livekit_api_key or "",
            app_settings.livekit_api_secret or "",
        )
    else:
        app.state.voice_provider = NoopVoiceProvider()
    app.include_router(http_router)
    app.include_router(ws_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
