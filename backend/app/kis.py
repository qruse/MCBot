from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

Region = Literal["domestic", "overseas"]
ChartRange = Literal["LIVE", "1D", "1W", "1M", "1Y", "5Y", "ALL"]

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


class KisChartCandle(BaseModel):
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
    source: str = "KIS Open API"


class KisChartResponse(BaseModel):
    source: str = "KIS Open API"
    environment: str
    symbol: str
    range: ChartRange
    interval: str
    count: int
    data: list[KisChartCandle]
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
_chart_cache: dict[tuple[str, ChartRange], tuple[float, KisChartResponse]] = {}


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


def _date_text(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_kis_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) != 8:
        return None

    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def _date_timestamp(value: date) -> str:
    return datetime(value.year, value.month, value.day, tzinfo=UTC).isoformat()


def _watchlist_symbol(symbol_code: str) -> KisSymbol:
    normalized_symbol = symbol_code.strip().upper()

    for symbol in WATCHLIST_SYMBOLS:
        if symbol.symbol == normalized_symbol:
            return symbol

    raise KisServiceError(f"{symbol_code}: unsupported watchlist symbol.", status_code=404)


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


def _chart_start_date(range_key: ChartRange) -> date:
    today = datetime.now(tz=UTC).date()
    days_by_range: dict[ChartRange, int] = {
        "LIVE": 1,
        "1D": 1,
        "1W": 14,
        "1M": 45,
        "1Y": 400,
        "5Y": 366 * 5 + 30,
        "ALL": 366 * 10,
    }

    return today - timedelta(days=days_by_range[range_key])


def _domestic_period_for(range_key: ChartRange) -> str:
    if range_key == "5Y":
        return "W"

    if range_key == "ALL":
        return "M"

    return "D"


def _overseas_period_for(range_key: ChartRange) -> str:
    if range_key == "5Y":
        return "1"

    if range_key == "ALL":
        return "2"

    return "0"


def _interval_label(range_key: ChartRange) -> str:
    if range_key in {"LIVE", "1D"}:
        return "intraday"

    if range_key == "5Y":
        return "weekly"

    if range_key == "ALL":
        return "monthly"

    return "daily"


def _domestic_chart_candle(symbol: KisSymbol, output: dict[str, Any]) -> KisChartCandle | None:
    candle_date = _parse_kis_date(output.get("stck_bsop_date"))

    if not candle_date:
        return None

    return KisChartCandle(
        symbol=symbol.symbol,
        timestamp=_date_timestamp(candle_date),
        open=_number(output.get("stck_oprc")),
        high=_number(output.get("stck_hgpr")),
        low=_number(output.get("stck_lwpr")),
        close=_number(output.get("stck_clpr")),
        volume=_int_or_none(output.get("acml_vol")),
    )


def _overseas_chart_candle(symbol: KisSymbol, output: dict[str, Any]) -> KisChartCandle | None:
    candle_date = _parse_kis_date(output.get("xymd"))

    if not candle_date:
        return None

    return KisChartCandle(
        symbol=symbol.symbol,
        timestamp=_date_timestamp(candle_date),
        open=_number(output.get("open")),
        high=_number(output.get("high")),
        low=_number(output.get("low")),
        close=_number(output.get("clos")),
        volume=_int_or_none(output.get("tvol")),
    )


def _dedupe_and_sort_candles(
    candles: list[KisChartCandle],
    start_date: date,
) -> list[KisChartCandle]:
    by_timestamp = {
        candle.timestamp: candle
        for candle in candles
        if candle.open and candle.high and candle.low and candle.close
    }
    filtered = [
        candle
        for candle in by_timestamp.values()
        if datetime.fromisoformat(candle.timestamp).date() >= start_date
    ]

    return sorted(filtered, key=lambda candle: candle.timestamp)


async def _fetch_domestic_chart(
    client: httpx.AsyncClient,
    access_token: str,
    symbol: KisSymbol,
    range_key: ChartRange,
) -> list[KisChartCandle]:
    start_date = _chart_start_date(range_key)
    end_date = datetime.now(tz=UTC).date()
    candles: list[KisChartCandle] = []

    for page in range(12):
        response = await client.get(
            f"{_kis_base_url()}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=_headers(access_token, "FHKST03010100"),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol.symbol,
                "FID_INPUT_DATE_1": _date_text(start_date),
                "FID_INPUT_DATE_2": _date_text(end_date),
                "FID_PERIOD_DIV_CODE": _domestic_period_for(range_key),
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        payload = response.json()
        _raise_for_kis(payload, symbol.symbol)

        rows = payload.get("output2") or []
        page_candles = [
            candle
            for row in rows
            if (candle := _domestic_chart_candle(symbol, row)) is not None
        ]
        candles.extend(page_candles)

        dates = [
            parsed_date
            for row in rows
            if (parsed_date := _parse_kis_date(row.get("stck_bsop_date"))) is not None
        ]

        if len(rows) < 100 or not dates or min(dates) <= start_date:
            break

        end_date = min(dates) - timedelta(days=1)
        await asyncio.sleep(_call_interval())

        if page > 0 and range_key in {"1W", "1M"}:
            break

    return _dedupe_and_sort_candles(candles, start_date)


async def _fetch_overseas_chart(
    client: httpx.AsyncClient,
    access_token: str,
    symbol: KisSymbol,
    range_key: ChartRange,
) -> list[KisChartCandle]:
    start_date = _chart_start_date(range_key)
    query_date = ""
    candles: list[KisChartCandle] = []

    for page in range(24):
        response = await client.get(
            f"{_kis_base_url()}/uapi/overseas-price/v1/quotations/dailyprice",
            headers=_headers(access_token, "HHDFS76240000"),
            params={
                "AUTH": "",
                "EXCD": symbol.exchange_code or "NAS",
                "SYMB": symbol.symbol,
                "GUBN": _overseas_period_for(range_key),
                "BYMD": query_date,
                "MODP": "0",
            },
        )
        payload = response.json()
        _raise_for_kis(payload, symbol.symbol)

        rows = payload.get("output2") or []
        page_candles = [
            candle
            for row in rows
            if (candle := _overseas_chart_candle(symbol, row)) is not None
        ]
        candles.extend(page_candles)

        dates = [
            parsed_date
            for row in rows
            if (parsed_date := _parse_kis_date(row.get("xymd"))) is not None
        ]

        if len(rows) < 100 or not dates or min(dates) <= start_date:
            break

        query_date = _date_text(min(dates) - timedelta(days=1))
        await asyncio.sleep(_call_interval())

        if page > 0 and range_key in {"1W", "1M"}:
            break

    return _dedupe_and_sort_candles(candles, start_date)


async def get_watchlist_chart(symbol_code: str, range_key: ChartRange) -> KisChartResponse:
    cache_key = (symbol_code.strip().upper(), range_key)
    cache_ttl = 60 if range_key in {"1W", "1M"} else 300
    now = time.monotonic()

    if cache_key in _chart_cache and now - _chart_cache[cache_key][0] < cache_ttl:
        return _chart_cache[cache_key][1]

    symbol = _watchlist_symbol(symbol_code)

    async with httpx.AsyncClient(timeout=30) as client:
        access_token = await _access_token_for(client)

        if symbol.region == "domestic":
            candles = await _fetch_domestic_chart(client, access_token, symbol, range_key)
        else:
            candles = await _fetch_overseas_chart(client, access_token, symbol, range_key)

    response = KisChartResponse(
        environment=_kis_environment(),
        symbol=symbol.symbol,
        range=range_key,
        interval=_interval_label(range_key),
        count=len(candles),
        data=candles,
        errors=[],
    )
    _chart_cache[cache_key] = (time.monotonic(), response)

    return response


async def get_watchlist_quotes(force_refresh: bool = False) -> KisWatchlistResponse:
    global _quote_cache

    now = time.monotonic()
    if (
        not force_refresh
        and _quote_cache
        and now - _quote_cache[0] < KIS_QUOTE_CACHE_TTL_SECONDS
    ):
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
