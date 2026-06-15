from __future__ import annotations

import asyncio
import math
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
KIS_TOKEN_REQUEST_COOLDOWN_SECONDS = 65.0
YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_CHART_SOURCE = "Yahoo Finance chart download"


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
_access_token_retry_after = 0.0
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


def _universe_symbol(symbol_code: str) -> KisSymbol | None:
    normalized_symbol = symbol_code.strip().upper()

    try:
        from app.universe import get_theme_universe
    except Exception:
        return None

    for theme in get_theme_universe(mode="all").themes:
        for holding in theme.top_market_cap:
            if holding.symbol.upper() == normalized_symbol:
                exchange_code = None
                if holding.region == "overseas":
                    exchange_code = {
                        "NASDAQ": "NAS",
                        "NYSE": "NYS",
                        "NYSEARCA": "AMS",
                        "NYSEAMERICAN": "AMS",
                        "BATS": "AMS",
                    }.get(holding.market.upper())

                return KisSymbol(
                    symbol=holding.symbol.upper(),
                    name=holding.name,
                    local_name=holding.local_name,
                    market=holding.market,
                    region=holding.region,
                    currency=holding.currency,
                    sector=holding.sector,
                    sector_ko=holding.sector_ko,
                    exchange_code=exchange_code,
                )

    return None


def _chart_symbol(symbol_code: str) -> KisSymbol:
    normalized_symbol = symbol_code.strip().upper()

    for symbol in WATCHLIST_SYMBOLS:
        if symbol.symbol == normalized_symbol:
            return symbol

    if symbol := _universe_symbol(normalized_symbol):
        return symbol

    if normalized_symbol.isdigit() and len(normalized_symbol) == 6:
        return KisSymbol(
            symbol=normalized_symbol,
            name=normalized_symbol,
            local_name=normalized_symbol,
            market="KOSPI",
            region="domestic",
            currency="KRW",
            sector="Unknown",
            sector_ko="Unknown",
        )

    return KisSymbol(
        symbol=normalized_symbol,
        name=normalized_symbol,
        local_name=normalized_symbol,
        market="US",
        region="overseas",
        currency="USD",
        sector="Unknown",
        sector_ko="Unknown",
    )


def _is_watchlist_symbol(symbol: KisSymbol) -> bool:
    return any(item.symbol == symbol.symbol for item in WATCHLIST_SYMBOLS)


async def _access_token_for(client: httpx.AsyncClient) -> str:
    global _access_token, _access_token_expires_at, _access_token_retry_after

    now = time.monotonic()
    if _access_token and now < _access_token_expires_at:
        return _access_token

    if now < _access_token_retry_after:
        raise KisServiceError(
            "KIS token endpoint is temporarily unavailable. Try again shortly.",
            status_code=503,
        )

    app_key = _credential("KIS_APP_KEY")
    app_secret = _credential("KIS_APP_SECRET")
    try:
        response = await client.post(
            f"{_kis_base_url()}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
        )
    except Exception as exc:
        _access_token_retry_after = now + KIS_TOKEN_REQUEST_COOLDOWN_SECONDS
        raise KisServiceError("Failed to request KIS token.", status_code=502) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        _access_token_retry_after = now + KIS_TOKEN_REQUEST_COOLDOWN_SECONDS
        raise KisServiceError(
            f"KIS token request returned invalid JSON: HTTP {response.status_code}",
            status_code=502,
        ) from exc

    if response.status_code >= 400 or not payload.get("access_token"):
        _access_token_retry_after = now + KIS_TOKEN_REQUEST_COOLDOWN_SECONDS
        raise KisServiceError(
            payload.get("error_description")
            or payload.get("msg1")
            or f"KIS token request failed: HTTP {response.status_code}",
            status_code=502,
        )

    _access_token = str(payload["access_token"])
    expires_in = int(payload.get("expires_in") or 60 * 60 * 23)
    _access_token_retry_after = 0.0
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


def _download_start_date(range_key: ChartRange) -> date:
    if range_key == "1D":
        return datetime.now(tz=UTC).date() - timedelta(days=7)

    return _chart_start_date(range_key)


def _minimum_chart_points(range_key: ChartRange) -> int:
    return {
        "LIVE": 2,
        "1D": 12,
        "1W": 5,
        "1M": 10,
        "1Y": 100,
        "5Y": 80,
        "ALL": 60,
    }[range_key]


def _yahoo_symbol(symbol: KisSymbol) -> str:
    if symbol.region == "overseas":
        return symbol.symbol.replace(".", "-")

    suffix = ".KQ" if symbol.market.upper() == "KOSDAQ" else ".KS"
    return f"{symbol.symbol}{suffix}"


def _yahoo_range_and_interval(range_key: ChartRange) -> tuple[str, str, str]:
    if range_key in {"LIVE", "1D"}:
        return "5d", "30m", "30m"

    if range_key == "1W":
        return "1mo", "1d", "daily"

    if range_key == "1M":
        return "3mo", "1d", "daily"

    if range_key == "1Y":
        return "1y", "1d", "daily"

    if range_key == "5Y":
        return "5y", "1wk", "weekly"

    return "10y", "1mo", "monthly"


def _finite_price(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) and number > 0 else None


def _yahoo_candles_from_payload(
    symbol: KisSymbol,
    range_key: ChartRange,
    payload: dict[str, Any],
) -> list[KisChartCandle]:
    chart = payload.get("chart") or {}
    errors = chart.get("error")
    if errors:
        raise KisServiceError(f"{symbol.symbol}: Yahoo chart error: {errors}", status_code=502)

    results = chart.get("result") or []
    if not results:
        return []

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    start_date = _download_start_date(range_key)
    candles: list[KisChartCandle] = []

    for index, epoch_seconds in enumerate(timestamps):
        open_price = _finite_price(opens[index] if index < len(opens) else None)
        high_price = _finite_price(highs[index] if index < len(highs) else None)
        low_price = _finite_price(lows[index] if index < len(lows) else None)
        close_price = _finite_price(closes[index] if index < len(closes) else None)

        if not all((open_price, high_price, low_price, close_price)):
            continue

        timestamp = datetime.fromtimestamp(int(epoch_seconds), tz=UTC)
        if timestamp.date() < start_date:
            continue

        raw_volume = volumes[index] if index < len(volumes) else None
        volume = int(raw_volume) if isinstance(raw_volume, int | float) else None

        candles.append(
            KisChartCandle(
                symbol=symbol.symbol,
                timestamp=timestamp.isoformat(),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                source=YAHOO_CHART_SOURCE,
            )
        )

    return sorted(candles, key=lambda candle: candle.timestamp)


async def _fetch_yahoo_chart(
    client: httpx.AsyncClient,
    symbol: KisSymbol,
    range_key: ChartRange,
) -> list[KisChartCandle]:
    yahoo_range, interval, _ = _yahoo_range_and_interval(range_key)
    response = await client.get(
        f"{YAHOO_CHART_BASE_URL}/{_yahoo_symbol(symbol)}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
        },
        params={
            "range": yahoo_range,
            "interval": interval,
            "includeAdjustedClose": "true",
            "events": "div,splits",
        },
    )

    if response.status_code >= 400:
        raise KisServiceError(
            f"{symbol.symbol}: Yahoo chart request failed: HTTP {response.status_code}",
            status_code=502,
        )

    return _yahoo_candles_from_payload(symbol, range_key, response.json())


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

    symbol = _chart_symbol(symbol_code)
    candles: list[KisChartCandle] = []
    source = "KIS Open API"
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        if _is_watchlist_symbol(symbol):
            try:
                access_token = await _access_token_for(client)

                if symbol.region == "domestic":
                    candles = await _fetch_domestic_chart(client, access_token, symbol, range_key)
                else:
                    candles = await _fetch_overseas_chart(client, access_token, symbol, range_key)
            except KisServiceError as exc:
                errors.append(exc.message)

        if len(candles) < _minimum_chart_points(range_key):
            try:
                downloaded_candles = await _fetch_yahoo_chart(client, symbol, range_key)
            except KisServiceError as exc:
                errors.append(exc.message)
            else:
                if downloaded_candles:
                    candles = downloaded_candles
                    source = YAHOO_CHART_SOURCE

    if not candles and not errors:
        errors.append(f"{symbol.symbol}: no historical candles returned.")

    response = KisChartResponse(
        source=source,
        environment=_kis_environment(),
        symbol=symbol.symbol,
        range=range_key,
        interval=(
            _yahoo_range_and_interval(range_key)[2]
            if source == YAHOO_CHART_SOURCE
            else _interval_label(range_key)
        ),
        count=len(candles),
        data=candles,
        errors=errors,
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
