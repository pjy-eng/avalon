from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_config_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "avalon-online-v2",
        "database": "not_configured",
        "redis": "not_configured",
        "voice": "not_configured",
    }
