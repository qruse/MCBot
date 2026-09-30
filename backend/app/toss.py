"""Read-only Toss integration. Paper orders never reach the brokerage."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/brokers/toss", tags=["Toss Securities"])
BASE_URL = "https://openapi.tossinvest.com"
_token: str | None = None
_expires_at = 0.0
_retry_at = 0.0
_lock = asyncio.Lock()
_last_call = 0.0
_history: dict[str, tuple[float, dict[str, Any]]] = {}
_cache: dict[str, tuple[float, str, Any]] = {}


async def _pace() -> None:
    """Serialize all outgoing calls, including OAuth: at most 20 per rolling minute."""
    global _last_call
    await asyncio.sleep(max(0, 3.1 - (time.monotonic() - _last_call)))
    _last_call = time.monotonic()


def _cache_key(path: str, params: dict[str, Any] | None) -> str:
    return f"{path}:{sorted((params or {}).items())}"


def configured() -> bool:
    return all(os.getenv(key, "").strip() for key in ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"))


async def _json(response: httpx.Response) -> dict[str, Any]:
    global _retry_at
    if response.status_code >= 400:
        if response.status_code in (401, 403):
            _retry_at = float("inf")
        elif response.status_code == 429:
            try:
                retry_seconds = float(response.headers.get("Retry-After", "300"))
            except ValueError:
                retry_seconds = 300
            _retry_at = time.monotonic() + max(300, retry_seconds)
        messages = {
            401: "Toss authentication failed. Check the local credentials.",
            403: "Toss access denied. Check the server's allowed public IP.",
            429: "Toss rate limit reached. Retry later.",
        }
        raise HTTPException(
            status_code=503 if response.status_code == 429 else 502,
            detail=messages.get(response.status_code, "Toss request failed."),
        )
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except ValueError as error:
        raise HTTPException(502, "Toss returned an invalid response.") from error


async def _request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    ttl: int = 0,
) -> Any:
    global _token, _expires_at, _retry_at
    if not configured():
        raise HTTPException(503, "Set TOSS_CLIENT_ID and TOSS_CLIENT_SECRET in backend/.env.")
    async with _lock:
        key = _cache_key(path, params)
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < ttl:
            return cached[2]
        if time.monotonic() < _retry_at:
            message = (
                "Toss calls paused. Fix credentials/allowed IP and restart the backend."
                if _retry_at == float("inf")
                else "Toss calls paused during cooldown. Retry later."
            )
            raise HTTPException(503, message)
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                if not _token or time.monotonic() >= _expires_at:
                    await _pace()
                    payload = await _json(
                        await client.post(
                            f"{BASE_URL}/oauth2/token",
                            data={
                                "grant_type": "client_credentials",
                                "client_id": os.environ["TOSS_CLIENT_ID"],
                                "client_secret": os.environ["TOSS_CLIENT_SECRET"],
                            },
                        )
                    )
                    if not payload.get("access_token"):
                        raise HTTPException(502, "Toss did not return an access token.")
                    _token = payload["access_token"]
                    _expires_at = time.monotonic() + max(0, int(payload["expires_in"]) - 60)
                await _pace()
                response = await client.get(
                    f"{BASE_URL}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {_token}"},
                )
                if response.status_code == 401:
                    _token = None
                payload = await _json(response)
                if "result" not in payload:
                    raise HTTPException(502, "Toss response is missing result data.")
                if ttl:
                    _cache[key] = (
                        time.monotonic(),
                        datetime.now(UTC).isoformat(),
                        payload["result"],
                    )
                return payload["result"]
        except httpx.HTTPError as error:
            _retry_at = max(_retry_at, time.monotonic() + 60)
            raise HTTPException(502, "Unable to reach Toss Securities.") from error
        except HTTPException:
            _retry_at = max(_retry_at, time.monotonic() + 60)
            raise


@router.get("status")
def status() -> dict[str, Any]:
    return {
        "configured": configured(),
        "execution": "local-paper",
        "provider": "Toss Securities",
        "quote_poll_seconds": 30,
        "strategy_refresh_seconds": 900,
    }


@router.get("connection")
async def connection() -> dict[str, Any]:
    accounts = await _request("/api/v1/accounts", ttl=300)
    return {
        "connected": True,
        "execution": "local-paper",
        "accounts": [{"account_seq": a["accountSeq"], "type": a["accountType"]} for a in accounts],
    }


@router.get("prices")
async def prices(symbols: str = Query(pattern=r"^[A-Za-z0-9.,\-]+$", max_length=2000)) -> Any:
    if not 1 <= len(symbols.split(",")) <= 200:
        raise HTTPException(422, "Request between 1 and 200 symbols.")
    params = {"symbols": ",".join(sorted(set(symbols.split(","))))}
    data = await _request("/api/v1/prices", params, ttl=30)
    synced_at = _cache[_cache_key("/api/v1/prices", params)][1]
    fx = await _request("/api/v1/exchange-rate", ttl=300)
    return {
        "data": data,
        "usd_krw": fx["rate"],
        "source": "Toss Securities Open API",
        "synced_at": synced_at,
    }


@router.get("strategy/{symbol}")
async def strategy(symbol: str) -> dict[str, Any]:
    if (
        not symbol
        or len(symbol) > 20
        or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in symbol)
    ):
        raise HTTPException(422, "Invalid symbol.")
    cached = _history.get(symbol)
    if cached and time.monotonic() - cached[0] < 900:
        return cached[1]
    minute_params = {"symbol": symbol, "interval": "1m", "count": 120}
    minute = await _request("/api/v1/candles", minute_params, ttl=900)
    daily = await _request(
        "/api/v1/candles",
        {"symbol": symbol, "interval": "1d", "count": 120},
        ttl=3600,
    )
    result = {
        "minute": sorted(minute["candles"], key=lambda c: c["timestamp"]),
        "daily": sorted(daily["candles"], key=lambda c: c["timestamp"]),
        "synced_at": _cache[_cache_key("/api/v1/candles", minute_params)][1],
    }
    _history[symbol] = (time.monotonic(), result)
    return result
