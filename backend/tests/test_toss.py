import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import toss


@pytest.fixture()
def requests(monkeypatch: pytest.MonkeyPatch, tmp_path) -> list[httpx.Request]:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 86400})
        if request.url.path == "/api/v1/prices":
            overseas = request.url.params["symbols"] == "NVDA"
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "symbol": "NVDA" if overseas else "005930",
                            "lastPrice": "145" if overseas else "72000",
                            "currency": "USD" if overseas else "KRW",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ]
                },
            )
        if request.url.path == "/api/v1/exchange-rate":
            assert dict(request.url.params) == {"baseCurrency": "USD", "quoteCurrency": "KRW"}
            return httpx.Response(200, json={"result": {
                "rate": "1380.5",
                "validFrom": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "validUntil": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }})
        if request.url.path == "/api/v1/accounts":
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "accountSeq": 1,
                            "accountType": "BROKERAGE",
                            "accountNo": "private",
                        }
                    ]
                },
            )
        if request.url.path == "/api/v1/stocks":
            return httpx.Response(200, json={"result": [
                {"symbol": "035420", "market": "KOSPI", "currency": "KRW", "status": "ACTIVE"},
                {"symbol": "UNREQUESTED", "market": "NASDAQ"},
            ]})
        if request.url.path == "/api/v1/market-calendar/KR":
            return httpx.Response(200, json={"result": {
                "today": {"date": "2026-09-30", "integrated": None},
                "previousBusinessDay": {"date": "2026-09-29"},
                "nextBusinessDay": {"date": "2026-10-01"},
            }})
        return httpx.Response(403, json={"error": {"message": "private-secret"}})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setenv("TOSS_CLIENT_ID", "test-id")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "test-secret")

    async def no_pacing():
        pass

    monkeypatch.setattr(toss, "_pace", no_pacing)
    monkeypatch.setattr(toss, "_cache", {})
    monkeypatch.setattr(toss, "_history", {})
    monkeypatch.setattr(toss, "_token", None)
    monkeypatch.setattr(toss, "_retry_at", 0)
    monkeypatch.setattr(toss, "_last_call", 0)
    monkeypatch.setattr(toss, "_provider_wait_at", 0)
    monkeypatch.setattr(toss, "_rate_limit_failures", 0)
    monkeypatch.setattr(toss, "_throttle_path", tmp_path / ".toss-throttle.json")
    monkeypatch.setattr(toss, "_lock", asyncio.Lock())
    return calls


def test_prices_reuses_token_and_connection_hides_account_number(requests):
    async def run():
        prices = await toss.prices("005930,000660")
        connection = await toss.connection()
        assert prices["data"][0]["lastPrice"] == "72000"
        assert prices["usd_krw"] is None
        assert prices["fx_quality"] is None
        assert prices["quality"]["005930"]["valid"]
        assert prices["quality"]["000660"]["reasons"] == ["missing_quote"]
        assert connection["accounts"] == [{"account_seq": 1, "type": "BROKERAGE"}]

    asyncio.run(run())
    assert sum(request.url.path == "/oauth2/token" for request in requests) == 1
    assert all(request.method == "GET" for request in requests if "token" not in request.url.path)
    assert all(request.url.path != "/api/v1/exchange-rate" for request in requests)


def test_missing_credentials_never_calls_broker(monkeypatch, requests):
    monkeypatch.delenv("TOSS_CLIENT_SECRET")
    with pytest.raises(HTTPException) as error:
        asyncio.run(toss.prices("005930"))
    assert error.value.status_code == 503
    assert requests == []


def test_stock_metadata_is_filtered_cached_and_read_only(requests):
    async def run():
        first = await toss.stocks(["035420"])
        assert first["data"] == [
            {"symbol": "035420", "market": "KOSPI", "currency": "KRW", "status": "ACTIVE"}
        ]
        assert first["synced_at"]
        assert await toss.stocks(["035420"]) == first

    asyncio.run(run())
    calls = [request for request in requests if request.url.path == "/api/v1/stocks"]
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.params["symbols"] == "035420"


def test_errors_redacted_and_requests_back_off(requests):
    async def run():
        with pytest.raises(HTTPException) as error:
            await toss._request("/denied")
        assert "allowed public IP" in error.value.detail
        assert error.value.headers["X-Toss-State"] == "authentication_error"
        assert "private-secret" not in error.value.detail
        before = len(requests)
        with pytest.raises(HTTPException) as retry:
            await toss._request("/denied")
        assert retry.value.status_code == 503
        assert len(requests) == before

    asyncio.run(run())


def test_cache_deduplicates_repeated_price_and_connection_requests(requests):
    async def run():
        first = await toss.prices("005930")
        second = await toss.prices("005930")
        await toss.connection()
        await toss.connection()
        assert first == second

    asyncio.run(run())
    assert len(requests) == 3  # OAuth, batch prices, accounts; no domestic FX dependency.


def test_overseas_fx_has_independent_source_and_receipt_times(requests):
    result = asyncio.run(toss.prices("NVDA"))
    assert result["usd_krw"] == "1380.5"
    assert result["fx_quality"]["valid"]
    assert result["fx_quality"]["source_at"] != result["quality"]["NVDA"]["source_at"]
    assert result["fx_quality"]["received_at"]


def test_invalid_and_stale_sources_are_not_revalidated_by_recent_receipt():
    now = datetime.now(UTC).isoformat()
    quality = toss._quote_quality({"lastPrice": "NaN", "currency": "KRW",
                                   "timestamp": "2020-01-01T00:00:00+00:00"}, now)
    assert not quality["valid"]
    assert quality["reasons"] == ["invalid_price", "stale_or_invalid_price_source"]
    assert quality["received_at"] == now
    fx = {"lastPrice": "100", "currency": "USD", "timestamp": now}
    assert toss._quote_quality(fx, now)["valid"]


def test_candle_quality_counts_only_closed_valid_candles():
    now = datetime.now(UTC)
    def candle(timestamp, price="10"):
        return {"timestamp": timestamp.isoformat(), "openPrice": price,
                "highPrice": price, "lowPrice": price, "closePrice": price}
    result = toss._history_quality([
        candle(now - timedelta(minutes=2)), candle(now - timedelta(minutes=1), "Infinity"),
        candle(now),
    ], now.isoformat(), "1m")
    assert result["complete_count"] == 1
    assert not result["valid_values"]
    assert not result["calendar_validated"]
    with pytest.raises(HTTPException) as error:
        toss._candles({"candles": "invalid"})
    assert error.value.status_code == 502


def test_rate_limit_uses_retry_after_and_stops_outbound_calls(monkeypatch, requests):
    async def run():
        with pytest.raises(HTTPException) as error:
            await toss._json(httpx.Response(429, headers={"Retry-After": "600"}))
        assert int(error.value.headers["Retry-After"]) >= 600
        assert toss._retry_at >= toss.time.monotonic() + 599
        with pytest.raises(HTTPException):
            await toss._request("/api/v1/prices")
        assert requests == []

    asyncio.run(run())


def test_pacing_includes_token_and_enforces_global_spacing(monkeypatch):
    clock = [100.0]
    waits = []

    async def advance(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(toss.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(toss.asyncio, "sleep", advance)
    monkeypatch.setattr(toss, "_last_call", 100.0)

    async def run():
        await toss._pace()
        await toss._pace()

    asyncio.run(run())
    assert waits == pytest.approx([6.1, 6.1])


def test_provider_headers_and_repeated_limits_extend_persistent_cooldown(requests):
    async def run():
        await toss._json(httpx.Response(200, headers={
            "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "12",
        }, json={"result": []}))
        assert toss._provider_wait_at >= toss.time.monotonic() + 11
        for _ in range(2):
            with pytest.raises(HTTPException):
                await toss._json(httpx.Response(429, headers={"Retry-After": "1"}))
        assert toss._restore_throttle() >= toss.time.monotonic() + 599
        with pytest.raises(HTTPException):
            await toss._request("/api/v1/prices")
        assert requests == []

    asyncio.run(run())


def test_calendar_is_cached_by_market_and_date_without_account_access(requests):
    async def run():
        first = await toss.calendar("KR")
        assert first == await toss.calendar("KR")
        assert first["data"]["today"]["integrated"] is None
        assert first["synced_at"]
        assert toss.status()["state"] == "ready"

    asyncio.run(run())
    assert len(requests) == 2  # OAuth plus one cached calendar; no accounts or orders.


def test_http_routes_match_frontend_urls(requests):
    application = FastAPI()
    application.include_router(toss.router)
    with TestClient(application) as client:
        assert client.get("/brokers/toss/status").json()["configured"]
        assert requests == []
        assert client.get("/brokers/toss/calendar/KR").status_code == 200
        assert client.get("/brokers/toss/prices?symbols=005930").status_code == 200
        paths = client.get("/openapi.json").json()["paths"]
        assert "/brokers/toss/strategy/{symbol}" in paths
        assert "/brokers/toss/connection" in paths
    assert len(requests) == 3  # OAuth, calendar, prices; no account or order request.


def test_fx_cache_never_outlives_provider_validity(requests):
    async def run():
        await toss.prices("NVDA")
        key = toss._cache_key("/api/v1/exchange-rate",
                              {"baseCurrency": "USD", "quoteCurrency": "KRW"})
        toss._cache[key][2]["validUntil"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        assert (await toss.prices("NVDA"))["fx_quality"]["valid"]

    asyncio.run(run())
    assert sum(call.url.path == "/api/v1/prices" for call in requests) == 1
    assert sum(call.url.path == "/api/v1/exchange-rate" for call in requests) == 2
