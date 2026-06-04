from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def test_read_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Money Copy Bot backend is running."


def test_read_health() -> None:
    main.ping_mongo = lambda: {
        "status": "ok",
        "database": "mcbot",
        "message": "MongoDB connection is healthy.",
    }

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "mcbot-backend",
        "version": "0.1.0",
        "database": {
            "status": "ok",
            "database": "mcbot",
            "message": "MongoDB connection is healthy.",
        },
    }
