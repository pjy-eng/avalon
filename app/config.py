from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str = "avalon-online-v2"
    database_url: str | None = None
    redis_url: str | None = None
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    session_secret: str = "dev-only-session-secret"

    @property
    def database_status(self) -> str:
        return "configured" if self.database_url else "not_configured"

    @property
    def redis_status(self) -> str:
        return "configured" if self.redis_url else "not_configured"

    @property
    def voice_status(self) -> str:
        if self.livekit_url and self.livekit_api_key and self.livekit_api_secret:
            return "configured"
        return "not_configured"


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL"),
        redis_url=os.getenv("REDIS_URL"),
        livekit_url=os.getenv("LIVEKIT_URL"),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY"),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET"),
        session_secret=os.getenv("SESSION_SECRET", "dev-only-session-secret"),
    )
