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


def test_read_kis_watchlist_quotes() -> None:
    async def fake_watchlist_quotes() -> dict[str, object]:
        return {
            "source": "KIS Open API",
            "environment": "paper",
            "count": 1,
            "data": [
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA Corp.",
                    "local_name": "엔비디아",
                    "market": "NASDAQ",
                    "region": "overseas",
                    "currency": "USD",
                    "price": 214.75,
                    "change_amount": -8.07,
                    "change": -3.62,
                    "open": None,
                    "high": None,
                    "low": None,
                    "volume": 160907001,
                    "sector": "Semiconductors",
                    "sector_ko": "반도체",
                    "source": "KIS Open API",
                    "fetched_at": "2026-06-04T00:00:00+00:00",
                }
            ],
            "errors": [],
        }

    main.get_latest_or_refresh_watchlist_quotes = fake_watchlist_quotes

    response = client.get("/quotes/kis/watchlist")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["data"][0]["symbol"] == "NVDA"


def test_read_kis_watchlist_history_live() -> None:
    async def fake_live_chart_history(symbol: str, range_key: str) -> dict[str, object]:
        return {
            "source": "Mongo scheduled KIS quotes",
            "environment": "paper",
            "symbol": symbol,
            "range": range_key,
            "interval": "1m",
            "count": 1,
            "data": [
                {
                    "symbol": symbol,
                    "timestamp": "2026-06-05T00:00:00+00:00",
                    "open": 214.0,
                    "high": 215.0,
                    "low": 213.0,
                    "close": 214.75,
                    "volume": None,
                    "source": "Mongo scheduled KIS quotes",
                }
            ],
            "errors": [],
        }

    main.get_live_chart_history = fake_live_chart_history

    response = client.get("/quotes/kis/history/NVDA?range=LIVE")

    assert response.status_code == 200
    assert response.json()["symbol"] == "NVDA"
    assert response.json()["data"][0]["close"] == 214.75
