from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_config_status(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("LIVEKIT_URL", "wss://example")
    monkeypatch.setenv("LIVEKIT_API_KEY", "example-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "example-secret")
    client = TestClient(create_app(Settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "avalon-online-v2",
        "database": "not_configured",
        "redis": "not_configured",
        "voice": "not_configured",
    }


def test_create_app_serves_index_outside_repo_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    index_response = client.get("/")
    static_response = client.get("/static/style.css")

    assert index_response.status_code == 200
    assert "Avalon Online v2" in index_response.text
    assert static_response.status_code == 200
    assert ".app-shell" in static_response.text
