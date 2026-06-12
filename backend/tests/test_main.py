from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main, market_data
from app.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def noop_scheduler() -> None:
        return None

    monkeypatch.setattr(main, "start_market_data_scheduler", noop_scheduler)
    monkeypatch.setattr(main, "stop_market_data_scheduler", noop_scheduler)

    with TestClient(app) as test_client:
        yield test_client


def test_read_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Money Copy Bot backend is running."


def test_read_health(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "ping_mongo",
        lambda: {
            "status": "ok",
            "database": "mcbot",
            "message": "MongoDB connection is healthy.",
        },
    )

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


def test_read_kis_watchlist_quotes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_watchlist_quotes(force_refresh: bool = False) -> dict[str, object]:
        return {
            "source": "KIS Open API",
            "environment": "paper",
            "count": 1,
            "data": [
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA Corp.",
                    "local_name": "NVIDIA Corp.",
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
                    "sector_ko": "Semiconductors",
                    "source": "KIS Open API",
                    "fetched_at": "2026-06-04T00:00:00+00:00",
                }
            ],
            "errors": [],
        }

    monkeypatch.setattr(main, "get_latest_or_refresh_watchlist_quotes", fake_watchlist_quotes)

    response = client.get("/quotes/kis/watchlist")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["data"][0]["symbol"] == "NVDA"


def test_read_kis_watchlist_history_live(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr(main, "get_live_chart_history", fake_live_chart_history)

    response = client.get("/quotes/kis/history/NVDA?range=LIVE")

    assert response.status_code == 200
    assert response.json()["symbol"] == "NVDA"
    assert response.json()["data"][0]["close"] == 214.75


def test_read_theme_universe(client: TestClient) -> None:
    response = client.get("/universe/themes")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 4
    assert body["themes"][0]["key"] == "semiconductors"
    assert body["themes"][0]["top_market_cap"][0]["market_cap_rank"] == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 1),
        ("7", 7),
        ("not-a-number", 1),
    ],
)
def test_refresh_interval_seconds(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
    expected: int,
) -> None:
    monkeypatch.delenv("MARKET_DATA_REFRESH_SECONDS", raising=False)

    if value is not None:
        monkeypatch.setenv("MARKET_DATA_REFRESH_SECONDS", value)

    assert market_data.refresh_interval_seconds() == expected
