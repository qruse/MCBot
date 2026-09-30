"""Read-only Toss integration. Paper orders never reach the brokerage."""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/brokers/toss", tags=["Toss Securities"])
BASE_URL = "https://openapi.tossinvest.com"
_token: str | None = None
_expires_at = 0.0
_retry_at = 0.0
_lock = asyncio.Lock()
_last_call = 0.0
_provider_wait_at = 0.0
_rate_limit_failures = 0
_throttle_path = Path(__file__).resolve().parents[1] / ".toss-throttle.json"
_history: dict[str, tuple[float, dict[str, Any]]] = {}
_cache: dict[str, tuple[float, str, Any]] = {}


def _restore_throttle() -> float:
    try:
        until = float(json.loads(_throttle_path.read_text(encoding="utf-8"))["until"])
        return time.monotonic() + max(0, until - time.time()) if math.isfinite(until) else 0
    except (OSError, ValueError, TypeError, KeyError):
        return 0


def _save_throttle() -> None:
    """Persist no secrets, only the provider cooldown; restart must not bypass a 429."""
    until = time.time() + max(0, _retry_at - time.monotonic())
    temporary = _throttle_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"until": until}), encoding="utf-8")
    temporary.replace(_throttle_path)


_retry_at = _restore_throttle()


def _positive_decimal(value: Any) -> bool:
    try:
        number = Decimal(str(value))
        return number.is_finite() and number > 0
    except InvalidOperation:
        return False


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except ValueError:
        return None


def _quote_quality(quote: dict[str, Any], received_at: str) -> dict[str, Any]:
    source = _timestamp(quote.get("timestamp"))
    now = datetime.now(UTC)
    reasons = []
    if not _positive_decimal(quote.get("lastPrice")):
        reasons.append("invalid_price")
    if quote.get("currency") not in ("KRW", "USD"):
        reasons.append("invalid_currency")
    if not source or not -5 <= (now - source).total_seconds() <= 90:
        reasons.append("stale_or_invalid_price_source")
    return {
        "source_at": quote.get("timestamp"),
        "received_at": received_at,
        "valid": not reasons,
        "reasons": reasons,
    }


def _history_quality(candles: list[dict[str, Any]], received_at: str, interval: str) -> dict:
    now = datetime.now(UTC)
    duration = 60 if interval == "1m" else 86400
    complete = []
    invalid = False
    seen = set()
    for candle in candles:
        timestamp = _timestamp(candle.get("timestamp"))
        if not timestamp or not all(
            _positive_decimal(candle.get(field))
            for field in ("openPrice", "highPrice", "lowPrice", "closePrice")
        ):
            invalid = True
            continue
        if timestamp in seen:
            invalid = True
        seen.add(timestamp)
        high = Decimal(str(candle["highPrice"]))
        low = Decimal(str(candle["lowPrice"]))
        prices = [Decimal(str(candle[field])) for field in ("openPrice", "closePrice")]
        if high < max(prices) or low > min(prices) or high < low:
            invalid = True
            continue
        if (now - timestamp).total_seconds() >= duration:
            complete.append(candle)
    return {
        "received_at": received_at,
        "source_at": complete[-1].get("timestamp") if complete else None,
        "complete_count": len(complete),
        "valid_values": not invalid,
        "calendar_validated": False,
    }


def _candles(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("candles"), list):
        raise HTTPException(502, "Toss returned invalid candle data.")
    if any(not isinstance(candle, dict) for candle in payload["candles"]):
        raise HTTPException(502, "Toss returned invalid candle data.")
    return sorted(
        payload["candles"],
        key=lambda candle: _timestamp(candle.get("timestamp")) or datetime.min.replace(tzinfo=UTC),
    )


async def _pace() -> None:
    """Serialize all outgoing calls, including OAuth: at most 10 per rolling minute."""
    global _last_call
    await asyncio.sleep(max(0, 6.1 - (time.monotonic() - _last_call),
                            _provider_wait_at - time.monotonic()))
    _last_call = time.monotonic()


def _cache_key(path: str, params: dict[str, Any] | None) -> str:
    return f"{path}:{sorted((params or {}).items())}"


def configured() -> bool:
    return all(os.getenv(key, "").strip() for key in ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"))


async def _json(response: httpx.Response) -> dict[str, Any]:
    global _retry_at, _provider_wait_at, _rate_limit_failures
    try:
        remaining = float(response.headers.get("X-RateLimit-Remaining", "inf"))
        reset = float(response.headers.get("X-RateLimit-Reset", "0"))
        if remaining <= 1 and math.isfinite(reset) and reset > 0:
            _provider_wait_at = max(_provider_wait_at, time.monotonic() + reset)
            if reset > 30:
                _retry_at = max(_retry_at, _provider_wait_at)
                _save_throttle()
    except ValueError:
        pass
    if response.status_code >= 400:
        if response.status_code in (401, 403):
            _retry_at = float("inf")
        elif response.status_code == 429:
            try:
                retry_seconds = float(response.headers.get("Retry-After", "300"))
            except ValueError:
                retry_seconds = 300
            if not math.isfinite(retry_seconds):
                retry_seconds = 300
            _rate_limit_failures += 1
            backoff = min(3600, 300 * 2 ** min(_rate_limit_failures - 1, 4))
            _retry_at = max(_retry_at, time.monotonic() + max(backoff, retry_seconds))
            _save_throttle()
        messages = {
            401: "Toss authentication failed. Check the local credentials.",
            403: "Toss access denied. Check the server's allowed public IP.",
            429: "Toss rate limit reached. Retry later.",
        }
        raise HTTPException(
            status_code=503 if response.status_code == 429 else 502,
            detail=messages.get(response.status_code, "Toss request failed."),
            headers=_failure_headers(),
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
        raise HTTPException(503, "Set TOSS_CLIENT_ID and TOSS_CLIENT_SECRET in backend/.env.",
                            headers={"X-Toss-State": "authentication_error"})
    async with _lock:
        key = _cache_key(path, params)
        cached = _cache.get(key)
        valid_fx_cache = path != "/api/v1/exchange-rate" or (
            cached and isinstance(cached[2], dict)
            and (end := _timestamp(cached[2].get("validUntil")))
            and end > datetime.now(UTC)
        )
        if cached and time.monotonic() - cached[0] < ttl and valid_fx_cache:
            return cached[2]
        if time.monotonic() < _retry_at:
            message = (
                "Toss calls paused. Fix credentials/allowed IP and restart the backend."
                if _retry_at == float("inf")
                else "Toss calls paused during cooldown. Retry later."
            )
            raise HTTPException(503, message, headers=_failure_headers())
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
                if time.monotonic() < _retry_at:
                    raise HTTPException(503, "Toss calls paused during cooldown. Retry later.",
                                        headers=_failure_headers())
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
            raise HTTPException(502, "Unable to reach Toss Securities.",
                                headers=_failure_headers()) from error
        except HTTPException as error:
            _retry_at = max(_retry_at, time.monotonic() + 60)
            error.headers = {**(error.headers or {}), **_failure_headers()}
            raise


def _failure_headers() -> dict[str, str]:
    if _retry_at == float("inf"):
        return {"X-Toss-State": "authentication_error"}
    return {"X-Toss-State": "cooldown",
            "Retry-After": str(max(60, int(_retry_at - time.monotonic()) + 1))}


@router.get("/status")
def status() -> dict[str, Any]:
    return {
        "configured": configured(),
        "execution": "local-paper",
        "provider": "Toss Securities",
        "quote_poll_seconds": 30,
        "strategy_refresh_seconds": 900,
        "state": ("authentication_error" if not configured() or _retry_at == float("inf")
                  else "cooldown" if time.monotonic() < _retry_at else "ready"),
        "retry_after_seconds": (None if _retry_at == float("inf")
                                else max(0, int(_retry_at - time.monotonic()) + 1)),
    }


@router.get("/calendar/{market}")
async def calendar(market: str) -> dict[str, Any]:
    if market not in ("KR", "US"):
        raise HTTPException(422, "Invalid market.")
    zone = ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")
    params = {"date": datetime.now(zone).date().isoformat()}
    path = f"/api/v1/market-calendar/{market}"
    data = await _request(path, params, ttl=3600)
    if not isinstance(data, dict) or not all(
        isinstance(data.get(key), dict)
        for key in ("today", "previousBusinessDay", "nextBusinessDay")
    ):
        raise HTTPException(502, "Toss returned invalid calendar data.")
    return {"data": data, "synced_at": _cache[_cache_key(path, params)][1]}


@router.get("/connection")
async def connection() -> dict[str, Any]:
    accounts = await _request("/api/v1/accounts", ttl=300)
    return {
        "connected": True,
        "execution": "local-paper",
        "accounts": [{"account_seq": a["accountSeq"], "type": a["accountType"]} for a in accounts],
    }


@router.get("/prices")
async def prices(symbols: str = Query(pattern=r"^[A-Za-z0-9.,\-]+$", max_length=2000)) -> Any:
    if not 1 <= len(symbols.split(",")) <= 200:
        raise HTTPException(422, "Request between 1 and 200 symbols.")
    params = {"symbols": ",".join(sorted(set(symbols.split(","))))}
    data = await _request("/api/v1/prices", params, ttl=30)
    if not isinstance(data, list) or any(not isinstance(quote, dict) for quote in data):
        raise HTTPException(502, "Toss returned invalid price data.")
    data = [quote for quote in data if quote.get("symbol") in params["symbols"].split(",")]
    synced_at = _cache[_cache_key("/api/v1/prices", params)][1]
    quality = {quote["symbol"]: _quote_quality(quote, synced_at) for quote in data}
    for symbol in params["symbols"].split(","):
        quality.setdefault(symbol, {"source_at": None, "received_at": synced_at,
                                    "valid": False, "reasons": ["missing_quote"]})
    fx = None
    fx_quality = None
    # KRW valuation never depends on an unrelated FX request or its failure/cooldown.
    if any(quote.get("currency") == "USD" for quote in data):
        try:
            fx_params = {"baseCurrency": "USD", "quoteCurrency": "KRW"}
            fx = await _request("/api/v1/exchange-rate", fx_params, ttl=300)
            if not isinstance(fx, dict):
                raise HTTPException(502, "Toss returned invalid FX data.")
            received_at = _cache[_cache_key("/api/v1/exchange-rate", fx_params)][1]
            start = _timestamp(fx.get("validFrom"))
            end = _timestamp(fx.get("validUntil"))
            valid = bool(
                _positive_decimal(fx.get("rate"))
                and start and end and start <= datetime.now(UTC) <= end
            )
            fx_quality = {
                "source_at": fx.get("validFrom"), "valid_until": fx.get("validUntil"),
                "received_at": received_at, "valid": valid,
                "reason": None if valid else "invalid_or_expired_fx",
            }
        except HTTPException:
            fx_quality = {"valid": False, "reason": "fx_unavailable"}
    return {
        "data": data,
        "usd_krw": fx.get("rate") if fx and fx_quality["valid"] else None,
        "quality": quality,
        "fx_quality": fx_quality,
        "source": "Toss Securities Open API",
        "synced_at": synced_at,
        "provider_status": status(),
    }


@router.get("/strategy/{symbol}")
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
    daily_params = {"symbol": symbol, "interval": "1d", "count": 120}
    daily = await _request(
        "/api/v1/candles",
        daily_params,
        ttl=3600,
    )
    result = {
        "minute": _candles(minute),
        "daily": _candles(daily),
        "synced_at": _cache[_cache_key("/api/v1/candles", minute_params)][1],
    }
    result["quality"] = {
        "minute": _history_quality(result["minute"], result["synced_at"], "1m"),
        "daily": _history_quality(
            result["daily"], _cache[_cache_key("/api/v1/candles", daily_params)][1], "1d"
        ),
    }
    _history[symbol] = (time.monotonic(), result)
    return result


async def stocks(symbols: list[str]) -> dict[str, Any]:
    """Read-only reference data through the same global provider queue and cache."""
    if not 1 <= len(symbols) <= 200 or any(
        not symbol or len(symbol) > 20
        or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in symbol)
        for symbol in symbols
    ):
        raise HTTPException(422, "Invalid stock symbols.")
    params = {"symbols": ",".join(sorted(set(symbols)))}
    data = await _request("/api/v1/stocks", params, ttl=300)
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise HTTPException(502, "Toss returned invalid stock reference data.")
    return {"data": [item for item in data if item.get("symbol") in symbols],
            "synced_at": _cache[_cache_key("/api/v1/stocks", params)][1]}
