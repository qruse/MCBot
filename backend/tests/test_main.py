from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_read_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Money Copy Bot backend is running."


def test_read_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "mcbot-backend",
        "version": "0.1.0",
    }


def test_cors_allows_workers_dashboard() -> None:
    origin = "https://mcbot.qruse.workers.dev"
    response = client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_other_workers_sites() -> None:
    response = client.get("/health", headers={"Origin": "https://evil.qruse.workers.dev"})

    assert "access-control-allow-origin" not in response.headers
