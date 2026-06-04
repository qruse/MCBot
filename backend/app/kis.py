from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

Region = Literal["domestic", "overseas"]

KIS_REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
KIS_QUOTE_CACHE_TTL_SECONDS = 10
KIS_PAPER_CALL_INTERVAL_SECONDS = 1.05
KIS_REAL_CALL_INTERVAL_SECONDS = 0.12


class KisSymbol(BaseModel):
    symbol: str
    name: str
    local_name: str
    market: str
    region: Region
    currency: Literal["KRW", "USD"]
    sector: str
    sector_ko: str
    exchange_code: str | None = None


class KisQuote(BaseModel):
    symbol: str
    name: str
    local_name: str
    market: str
    region: Region
    currency: Literal["KRW", "USD"]
    price: float
    change_amount: float
    change: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    sector: str
    sector_ko: str
    source: str = "KIS Open API"
    fetched_at: str


class KisWatchlistResponse(BaseModel):
    source: str = "KIS Open API"
    environment: str
    count: int
    data: list[KisQuote]
    errors: list[str] = []


class KisServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


WATCHLIST_SYMBOLS: tuple[KisSymbol, ...] = (
    KisSymbol(
        symbol="NVDA",
        name="NVIDIA Corp.",
        local_name="엔비디아",
        market="NASDAQ",
        region="overseas",
        currency="USD",
        sector="Semiconductors",
        sector_ko="반도체",
        exchange_code="NAS",
    ),
    KisSymbol(
        symbol="MU",
        name="Micron Technology Inc.",
        local_name="마이크론",
        market="NASDAQ",
        region="overseas",
        currency="USD",
        sector="Memory Chips",
        sector_ko="메모리 반도체",
        exchange_code="NAS",
    ),
    KisSymbol(
        symbol="SNDK",
        name="Sandisk Corp.",
        local_name="샌디스크",
        market="NASDAQ",
        region="overseas",
        currency="USD",
        sector="Storage",
        sector_ko="스토리지",
        exchange_code="NAS",
    ),
    KisSymbol(
        symbol="005930",
        name="Samsung Electronics",
        local_name="삼성전자",
        market="KOSPI",
        region="domestic",
        currency="KRW",
        sector="Semiconductors",
        sector_ko="반도체",
    ),
    KisSymbol(
        symbol="000660",
        name="SK Hynix",
        local_name="SK하이닉스",
        market="KOSPI",
        region="domestic",
        currency="KRW",
        sector="Memory Chips",
        sector_ko="메모리 반도체",
    ),
)

_access_token: str | None = None
_access_token_expires_at = 0.0
_quote_cache: tuple[float, KisWatchlistResponse] | None = None


def _kis_environment() -> str:
    return os.getenv("KIS_ENV", "paper").strip().lower()


def _kis_base_url() -> str:
    return KIS_PAPER_BASE_URL if _kis_environment() == "paper" else KIS_REAL_BASE_URL


def _call_interval() -> float:
    return (
        KIS_PAPER_CALL_INTERVAL_SECONDS
        if _kis_environment() == "paper"
        else KIS_REAL_CALL_INTERVAL_SECONDS
    )


def _credential(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise KisServiceError(f"{name} is not configured.", status_code=503)

    return value


def _number(value: Any) -> float:
    text = str(value or "").replace(",", "").replace("+", "").strip()
    if not text or text == "-":
        return 0.0

    return float(text)


def _int_or_none(value: Any) -> int | None:
    text = str(value or "").replace(",", "").strip()
    if not text or text == "-":
        return None

    return int(float(text))


def _timestamp() -> str:
    return datetime.now(tz=UTC).isoformat()


async def _access_token_for(client: httpx.AsyncClient) -> str:
    global _access_token, _access_token_expires_at

    now = time.monotonic()
    if _access_token and now < _access_token_expires_at:
        return _access_token

    app_key = _credential("KIS_APP_KEY")
    app_secret = _credential("KIS_APP_SECRET")
    response = await client.post(
        f"{_kis_base_url()}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        },
    )
    payload = response.json()

    if response.status_code >= 400 or not payload.get("access_token"):
        raise KisServiceError(
            payload.get("error_description")
            or payload.get("msg1")
            or f"KIS token request failed: HTTP {response.status_code}",
            status_code=502,
        )

    _access_token = str(payload["access_token"])
    expires_in = int(payload.get("expires_in") or 60 * 60 * 23)
    _access_token_expires_at = now + max(60, expires_in - 300)

    return _access_token


def _headers(access_token: str, tr_id: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {access_token}",
        "appkey": _credential("KIS_APP_KEY"),
        "appsecret": _credential("KIS_APP_SECRET"),
        "tr_id": tr_id,
        "custtype": "P",
    }


def _raise_for_kis(payload: dict[str, Any], symbol: str) -> None:
    if payload.get("rt_cd") == "0":
        return

    raise KisServiceError(
        f"{symbol}: {payload.get('msg1') or payload.get('msg_cd') or 'KIS quote request failed.'}"
    )


def _domestic_quote_from_payload(symbol: KisSymbol, output: dict[str, Any]) -> KisQuote:
    return KisQuote(
        symbol=symbol.symbol,
        name=symbol.name,
        local_name=symbol.local_name,
        market=symbol.market,
        region=symbol.region,
        currency=symbol.currency,
        price=_number(output.get("stck_prpr")),
        change_amount=_number(output.get("prdy_vrss")),
        change=_number(output.get("prdy_ctrt")),
        open=_number(output.get("stck_oprc")),
        high=_number(output.get("stck_hgpr")),
        low=_number(output.get("stck_lwpr")),
        volume=_int_or_none(output.get("acml_vol")),
        sector=symbol.sector,
        sector_ko=symbol.sector_ko,
        fetched_at=_timestamp(),
    )


def _overseas_quote_from_payload(symbol: KisSymbol, output: dict[str, Any]) -> KisQuote:
    change = _number(output.get("rate"))
    change_amount = _number(output.get("diff"))

    if change < 0 and change_amount > 0:
        change_amount = -change_amount

    return KisQuote(
        symbol=symbol.symbol,
        name=symbol.name,
        local_name=symbol.local_name,
        market=symbol.market,
        region=symbol.region,
        currency=symbol.currency,
        price=_number(output.get("last")),
        change_amount=change_amount,
        change=change,
        volume=_int_or_none(output.get("tvol")),
        sector=symbol.sector,
        sector_ko=symbol.sector_ko,
        fetched_at=_timestamp(),
    )


async def _fetch_domestic_quote(
    client: httpx.AsyncClient,
    access_token: str,
    symbol: KisSymbol,
) -> KisQuote:
    response = await client.get(
        f"{_kis_base_url()}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers=_headers(access_token, "FHKST01010100"),
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol.symbol,
        },
    )
    payload = response.json()
    _raise_for_kis(payload, symbol.symbol)

    return _domestic_quote_from_payload(symbol, payload.get("output") or {})


async def _fetch_overseas_quote(
    client: httpx.AsyncClient,
    access_token: str,
    symbol: KisSymbol,
) -> KisQuote:
    response = await client.get(
        f"{_kis_base_url()}/uapi/overseas-price/v1/quotations/price",
        headers=_headers(access_token, "HHDFS00000300"),
        params={
            "AUTH": "",
            "EXCD": symbol.exchange_code or "NAS",
            "SYMB": symbol.symbol,
        },
    )
    payload = response.json()
    _raise_for_kis(payload, symbol.symbol)

    return _overseas_quote_from_payload(symbol, payload.get("output") or {})


async def get_watchlist_quotes() -> KisWatchlistResponse:
    global _quote_cache

    now = time.monotonic()
    if _quote_cache and now - _quote_cache[0] < KIS_QUOTE_CACHE_TTL_SECONDS:
        return _quote_cache[1]

    quotes: list[KisQuote] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=20) as client:
        access_token = await _access_token_for(client)

        for index, symbol in enumerate(WATCHLIST_SYMBOLS):
            if index > 0:
                await asyncio.sleep(_call_interval())

            try:
                if symbol.region == "domestic":
                    quotes.append(await _fetch_domestic_quote(client, access_token, symbol))
                else:
                    quotes.append(await _fetch_overseas_quote(client, access_token, symbol))
            except KisServiceError as exc:
                errors.append(exc.message)

    response = KisWatchlistResponse(
        environment=_kis_environment(),
        count=len(quotes),
        data=quotes,
        errors=errors,
    )
    _quote_cache = (time.monotonic(), response)

    return response
