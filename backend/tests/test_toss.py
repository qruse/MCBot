import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app import toss


@pytest.fixture()
def requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 86400})
        if request.url.path == "/api/v1/prices":
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "symbol": "005930",
                            "lastPrice": "72000",
                            "currency": "KRW",
                            "timestamp": "2026-09-30T09:30:00+09:00",
                        }
                    ]
                },
            )
        if request.url.path == "/api/v1/exchange-rate":
            return httpx.Response(200, json={"result": {"rate": "1380.5"}})
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
    monkeypatch.setattr(toss, "_lock", asyncio.Lock())
    return calls


def test_prices_reuses_token_and_connection_hides_account_number(requests):
    async def run():
        prices = await toss.prices("005930")
        connection = await toss.connection()
        assert prices["data"][0]["lastPrice"] == "72000"
        assert prices["usd_krw"] == "1380.5"
        assert connection["accounts"] == [{"account_seq": 1, "type": "BROKERAGE"}]

    asyncio.run(run())
    assert sum(request.url.path == "/oauth2/token" for request in requests) == 1
    assert all(request.method == "GET" for request in requests if "token" not in request.url.path)


def test_missing_credentials_never_calls_broker(monkeypatch, requests):
    monkeypatch.delenv("TOSS_CLIENT_SECRET")
    with pytest.raises(HTTPException) as error:
        asyncio.run(toss.prices("005930"))
    assert error.value.status_code == 503
    assert requests == []


def test_errors_redacted_and_requests_back_off(requests):
    async def run():
        with pytest.raises(HTTPException) as error:
            await toss._request("/denied")
        assert "allowed public IP" in error.value.detail
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
    assert len(requests) == 4  # OAuth, batch prices, FX, accounts; each only once.


def test_rate_limit_uses_retry_after_and_stops_outbound_calls(monkeypatch, requests):
    async def run():
        with pytest.raises(HTTPException):
            await toss._json(httpx.Response(429, headers={"Retry-After": "600"}))
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
    assert waits == pytest.approx([3.1, 3.1])
