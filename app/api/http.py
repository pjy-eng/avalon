from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.config import Settings

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str | bool]:
    settings: Settings = request.app.state.settings
    return {
        "ok": True,
        "service": settings.service_name,
        "database": settings.database_status,
        "redis": settings.redis_status,
        "voice": settings.voice_status,
    }


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
