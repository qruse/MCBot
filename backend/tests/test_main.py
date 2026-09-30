from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
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


def test_read_health(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "kis")
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


def test_startup_gap_fill_watchlist_history_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    symbols = tuple(
        kis.KisSymbol(
            symbol=f"SYM{i}",
            name=f"SYM{i}",
            local_name=f"SYM{i}",
            market="KOSPI",
            region="domestic",
            currency="KRW",
            sector="Test",
            sector_ko="Test",
        )
        for i in range(10)
    )
    monkeypatch.setattr(market_data, "WATCHLIST_SYMBOLS", symbols)

    captured: list[str] = []

    async def fake_downloaded_chart(symbol: str, range_key: kis.ChartRange) -> kis.KisChartResponse:
        captured.append(symbol)
        return kis.KisChartResponse(
            source=kis.YAHOO_CHART_SOURCE,
            environment="paper",
            symbol=symbol,
            range=range_key,
            interval="5m",
            count=0,
            data=[],
            errors=[],
        )

    monkeypatch.setattr(market_data, "_history_gap_needs_backfill_sync", lambda _: True)
    monkeypatch.setattr(market_data, "get_watchlist_chart", fake_downloaded_chart)
    monkeypatch.setattr(
        market_data,
        "_persist_gap_fill_history_sync",
        lambda _symbol, _candles: 0,
    )

    asyncio.run(market_data._startup_gap_fill_watchlist_history())

    assert len(captured) == 5


def test_start_market_data_scheduler_respects_env_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(market_data, "_scheduler_task", None)
    monkeypatch.setattr(market_data, "_background_refresh_task", None)
    monkeypatch.setenv("MARKET_DATA_SCHEDULER_ENABLED", "false")
    monkeypatch.setattr(market_data, "_scheduler_loop", lambda: asyncio.sleep(0.01))
    monkeypatch.setattr(
        market_data,
        "_startup_gap_fill_watchlist_history",
        lambda: asyncio.sleep(0),
    )

    asyncio.run(market_data.start_market_data_scheduler())

    assert market_data._scheduler_task is None


def test_get_latest_or_refresh_prefers_cached_data(monkeypatch: pytest.MonkeyPatch) -> None:
    quote = kis.KisWatchlistResponse(
        environment="paper",
        count=1,
        data=[
            kis.KisQuote(
                symbol="NVDA",
                name="NVIDIA Corp.",
                local_name="NVIDIA Corp.",
                market="NASDAQ",
                region="overseas",
                currency="USD",
                price=1.0,
                change_amount=0.0,
                change=0.0,
                sector="Semiconductors",
                sector_ko="Semiconductors",
                fetched_at=datetime(2026, 6, 1, tzinfo=UTC).isoformat(),
            )
        ],
        errors=[],
    )
    latest_time = datetime(2026, 6, 1, tzinfo=UTC) - timedelta(hours=1)
    old_task_flag = {"scheduled": 0}

    async def fake_schedule_background_refresh() -> None:
        old_task_flag["scheduled"] += 1

    async def fake_refresh() -> kis.KisWatchlistResponse:
        raise AssertionError("refresh_market_data should not be called when stale cache exists")

    monkeypatch.setattr(market_data, "_latest_snapshot_sync", lambda: (quote, latest_time))
    monkeypatch.setattr(
        market_data,
        "_schedule_background_market_refresh",
        fake_schedule_background_refresh,
    )
    monkeypatch.setattr(market_data, "refresh_market_data", fake_refresh)
    monkeypatch.setenv("MARKET_DATA_REFRESH_SECONDS", "10")

    result = asyncio.run(market_data.get_latest_or_refresh_watchlist_quotes())

    assert result == quote
    assert old_task_flag["scheduled"] == 1


def test_access_token_request_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    async def fake_post(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        attempts["count"] += 1
        raise RuntimeError("network fail")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(kis, "_access_token", None)
    monkeypatch.setattr(kis, "_access_token_expires_at", 0.0)
    monkeypatch.setattr(kis, "_access_token_retry_after", 0.0)
    monkeypatch.setattr(kis, "_credential", lambda _: "value")

    client = httpx.AsyncClient()

    with pytest.raises(kis.KisServiceError):
        asyncio.run(kis._access_token_for(client))

    with pytest.raises(kis.KisServiceError):
        asyncio.run(kis._access_token_for(client))

    assert attempts["count"] == 1


def test_access_token_invalid_json_response_uses_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    async def fake_post(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            429,
            content=b"Too Many Requests",
            request=httpx.Request("POST", "https://example.test/oauth2/tokenP"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(kis, "_access_token", None)
    monkeypatch.setattr(kis, "_access_token_expires_at", 0.0)
    monkeypatch.setattr(kis, "_access_token_retry_after", 0.0)
    monkeypatch.setattr(kis, "_credential", lambda _: "value")

    client = httpx.AsyncClient()

    with pytest.raises(kis.KisServiceError, match="invalid JSON"):
        asyncio.run(kis._access_token_for(client))

    with pytest.raises(kis.KisServiceError, match="temporarily unavailable"):
        asyncio.run(kis._access_token_for(client))

    assert attempts["count"] == 1
