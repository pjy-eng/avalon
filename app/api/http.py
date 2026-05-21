from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import Settings

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


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    with open("static/index.html", "r", encoding="utf-8") as file:
        return file.read()
