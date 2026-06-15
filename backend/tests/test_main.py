from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import kis, main, market_data
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


def test_read_one_day_history_downloads_when_live_history_is_sparse(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_live_chart_history(
        symbol: str,
        range_key: kis.ChartRange,
    ) -> kis.KisChartResponse:
        return kis.KisChartResponse(
            source="Mongo scheduled KIS quotes",
            environment="paper",
            symbol=symbol,
            range=range_key,
            interval="5m",
            count=1,
            data=[],
            errors=[],
        )

    async def fake_downloaded_chart(symbol: str, range_key: kis.ChartRange) -> kis.KisChartResponse:
        downloaded_data = [
            kis.KisChartCandle(
                symbol=symbol,
                timestamp=f"2026-06-{day:02d}T00:00:00+00:00",
                open=214.0,
                high=215.0,
                low=213.0,
                close=214.75,
                volume=100,
                source=kis.YAHOO_CHART_SOURCE,
            )
            for day in range(5, 17)
        ]

        return kis.KisChartResponse(
            source=kis.YAHOO_CHART_SOURCE,
            environment="paper",
            symbol=symbol,
            range=range_key,
            interval="30m",
            count=len(downloaded_data),
            data=downloaded_data,
            errors=[],
        )

    monkeypatch.setattr(main, "get_live_chart_history", fake_live_chart_history)
    monkeypatch.setattr(main, "get_watchlist_chart", fake_downloaded_chart)

    response = client.get("/quotes/kis/history/NVDA?range=1D")

    assert response.status_code == 200
    assert response.json()["source"] == kis.YAHOO_CHART_SOURCE
    assert response.json()["interval"] == "30m"


def test_get_theme_symbol_chart_uses_downloaded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kis._chart_cache.clear()

    async def fake_yahoo_chart(
        _client: object,
        symbol: kis.KisSymbol,
        _range_key: kis.ChartRange,
    ) -> list[kis.KisChartCandle]:
        assert symbol.symbol == "IONQ"
        return [
            kis.KisChartCandle(
                symbol=symbol.symbol,
                timestamp="2026-06-05T00:00:00+00:00",
                open=43.0,
                high=44.0,
                low=42.5,
                close=43.75,
                volume=1000,
                source=kis.YAHOO_CHART_SOURCE,
            )
        ]

    monkeypatch.setattr(kis, "_fetch_yahoo_chart", fake_yahoo_chart)

    response = asyncio.run(kis.get_watchlist_chart("IONQ", "1M"))

    assert response.source == kis.YAHOO_CHART_SOURCE
    assert response.interval == "daily"
    assert response.count == 1
    assert response.data[0].source == kis.YAHOO_CHART_SOURCE


def test_read_theme_universe(client: TestClient) -> None:
    response = client.get("/universe/themes")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 17
    assert body["themes"][0]["key"] == "semiconductors"
    assert body["themes"][0]["top_market_cap"][0]["market_cap_rank"] == 1
    themes_by_key = {theme["key"]: theme for theme in body["themes"]}
    assert themes_by_key["korea-semiconductors"]["name_ko"] == "국내 반도체"
    assert themes_by_key["korea-semiconductors"]["top_market_cap"][0]["symbol"] == "005930"
    assert themes_by_key["quantum-computing"]["name_ko"] == "양자컴퓨터"
    assert themes_by_key["us-inverse-etfs"]["top_market_cap"][0]["symbol"] == "SH"
    assert themes_by_key["korea-inverse-etfs"]["top_market_cap"][1]["symbol"] == "252670"
    assert len(themes_by_key["korea-inverse-etfs"]["top_market_cap"]) == 10


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
