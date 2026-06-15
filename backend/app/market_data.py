from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.database import get_collection
from app.kis import (
    WATCHLIST_SYMBOLS,
    ChartRange,
    KisChartCandle,
    KisChartResponse,
    KisQuote,
    KisServiceError,
    KisWatchlistResponse,
    _kis_environment,
    get_watchlist_chart,
    get_watchlist_quotes,
)

DEFAULT_REFRESH_SECONDS = 30
MIN_REFRESH_SECONDS = 5
DEFAULT_GAP_FILL_SYMBOLS = 5
GAP_FILL_RANGE_KEY: ChartRange = "1D"
GAP_FILL_MAX_CANDLES = 30
HISTORY_GAP_LOOKBACK_HOURS = 6
HISTORY_GAP_MIN_POINTS = 2
LATEST_COLLECTION = "market_quote_latest"
HISTORY_COLLECTION = "market_quote_history"
RUNS_COLLECTION = "market_refresh_runs"

_scheduler_task: asyncio.Task[None] | None = None
_refresh_lock: asyncio.Lock | None = None
_last_refresh_started_at = 0.0
_last_refresh_response: KisWatchlistResponse | None = None
_last_background_refresh_started_at = 0.0
_background_refresh_task: asyncio.Task[None] | None = None
_startup_gap_fill_completed = False
_indexes_ready = False
logger = logging.getLogger(__name__)


def refresh_interval_seconds() -> int:
    raw_value = os.getenv("MARKET_DATA_REFRESH_SECONDS", str(DEFAULT_REFRESH_SECONDS)).strip()

    try:
        return max(MIN_REFRESH_SECONDS, int(raw_value))
    except ValueError:
        return DEFAULT_REFRESH_SECONDS


def market_data_scheduler_enabled() -> bool:
    value = os.getenv("MARKET_DATA_SCHEDULER_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def startup_gap_fill_enabled() -> bool:
    value = os.getenv("STARTUP_GAP_FILL_ENABLED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _quote_document(quote: KisQuote, refresh_id: str, stored_at: datetime) -> dict[str, Any]:
    document = quote.model_dump()
    document["refresh_id"] = refresh_id
    document["stored_at"] = stored_at

    return document


def _live_chart_window(range_key: ChartRange) -> tuple[datetime, int]:
    now = _utc_now()

    if range_key == "LIVE":
        return now - timedelta(hours=2), 60

    return now - timedelta(hours=24), 300


def _bucket_timestamp(value: datetime, bucket_seconds: int) -> datetime:
    utc_value = _as_utc(value)
    epoch_seconds = int(utc_value.timestamp())
    bucket_epoch = epoch_seconds - (epoch_seconds % bucket_seconds)

    return datetime.fromtimestamp(bucket_epoch, tz=UTC)


def _live_chart_from_documents(
    symbol: str,
    range_key: ChartRange,
    documents: list[dict[str, Any]],
) -> KisChartResponse:
    _, bucket_seconds = _live_chart_window(range_key)
    buckets: dict[datetime, list[float]] = {}

    for document in documents:
        price = float(document.get("price") or 0)
        stored_at = document.get("stored_at")

        if price <= 0 or not isinstance(stored_at, datetime):
            continue

        bucket_at = _bucket_timestamp(stored_at, bucket_seconds)
        buckets.setdefault(bucket_at, []).append(price)

    candles = [
        KisChartCandle(
            symbol=symbol,
            timestamp=bucket_at.isoformat(),
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=None,
            source="Mongo scheduled KIS quotes",
        )
        for bucket_at, prices in sorted(buckets.items())
    ]

    return KisChartResponse(
        source="Mongo scheduled KIS quotes",
        environment=_kis_environment(),
        symbol=symbol,
        range=range_key,
        interval=f"{bucket_seconds // 60}m",
        count=len(candles),
        data=candles,
        errors=[],
    )


def _persist_response_sync(
    response: KisWatchlistResponse,
    refresh_id: str,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    global _indexes_ready

    latest_collection = get_collection(LATEST_COLLECTION)
    history_collection = get_collection(HISTORY_COLLECTION)
    runs_collection = get_collection(RUNS_COLLECTION)

    if not _indexes_ready:
        latest_collection.create_index(
            [("symbol", ASCENDING), ("region", ASCENDING)],
            unique=True,
            name="symbol_region_unique",
        )
        history_collection.create_index(
            [("symbol", ASCENDING), ("region", ASCENDING), ("stored_at", DESCENDING)],
            name="symbol_region_stored_at",
        )
        history_collection.create_index([("stored_at", DESCENDING)], name="stored_at_desc")
        runs_collection.create_index([("started_at", DESCENDING)], name="started_at_desc")
        _indexes_ready = True

    documents = [
        _quote_document(quote, refresh_id=refresh_id, stored_at=completed_at)
        for quote in response.data
    ]

    if documents:
        latest_collection.bulk_write(
            [
                UpdateOne(
                    {"symbol": document["symbol"], "region": document["region"]},
                    {"$set": document},
                    upsert=True,
                )
                for document in documents
            ]
        )
        history_collection.insert_many(documents)

    runs_collection.insert_one(
        {
            "refresh_id": refresh_id,
            "source": response.source,
            "environment": response.environment,
            "started_at": started_at,
            "completed_at": completed_at,
            "count": response.count,
            "errors": response.errors,
            "status": "ok" if response.data else "empty",
        }
    )


def _record_refresh_error_sync(
    refresh_id: str,
    started_at: datetime,
    completed_at: datetime,
    error: Exception,
) -> None:
    get_collection(RUNS_COLLECTION).insert_one(
        {
            "refresh_id": refresh_id,
            "source": "KIS Open API",
            "environment": _kis_environment(),
            "started_at": started_at,
            "completed_at": completed_at,
            "count": 0,
            "errors": [str(error)],
            "status": "error",
        }
    )


def _latest_snapshot_sync() -> tuple[KisWatchlistResponse, datetime | None]:
    collection = get_collection(LATEST_COLLECTION)
    documents = list(collection.find({}, {"_id": False}))
    symbol_order = {symbol.symbol: index for index, symbol in enumerate(WATCHLIST_SYMBOLS)}
    documents.sort(key=lambda document: symbol_order.get(str(document.get("symbol")), 999))

    quotes = [KisQuote(**document) for document in documents]
    stored_times = [
        _as_utc(stored_at)
        for document in documents
        if isinstance((stored_at := document.get("stored_at")), datetime)
    ]

    return (
        KisWatchlistResponse(
            environment=_kis_environment(),
            count=len(quotes),
            data=quotes,
            errors=[],
        ),
        max(stored_times) if stored_times else None,
    )


def _history_gap_needs_backfill_sync(symbol: str) -> bool:
    collection = get_collection(HISTORY_COLLECTION)
    cutoff = _utc_now() - timedelta(hours=HISTORY_GAP_LOOKBACK_HOURS)

    recent_count = collection.count_documents(
        {"symbol": symbol, "stored_at": {"$gte": cutoff.replace(tzinfo=None)}},
        limit=HISTORY_GAP_MIN_POINTS,
    )

    return recent_count < HISTORY_GAP_MIN_POINTS


def _persist_gap_fill_history_sync(symbol: str, candles: list[KisChartCandle]) -> int:
    if not candles:
        return 0

    metadata = None
    for watchlist_symbol in WATCHLIST_SYMBOLS:
        if watchlist_symbol.symbol == symbol:
            metadata = watchlist_symbol
            break

    history_collection = get_collection(HISTORY_COLLECTION)
    to_store: list[dict[str, Any]] = []

    for candle in candles[:GAP_FILL_MAX_CANDLES]:
        stored_at = datetime.fromisoformat(candle.timestamp)
        if stored_at.tzinfo is None:
            stored_at = stored_at.replace(tzinfo=UTC)

        existing = history_collection.find_one(
            {"symbol": symbol, "stored_at": stored_at},
            {"_id": True},
        )
        if existing:
            continue

        to_store.append(
            {
                "symbol": symbol,
                "stored_at": stored_at,
                "price": candle.close,
                "source": candle.source,
                "name": metadata.name if metadata else symbol,
                "local_name": metadata.local_name if metadata else symbol,
                "market": metadata.market if metadata else "KOSPI",
                "region": metadata.region if metadata else "domestic",
                "currency": metadata.currency if metadata else "KRW",
                "sector": metadata.sector if metadata else "Unknown",
                "sector_ko": metadata.sector_ko if metadata else "Unknown",
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "volume": candle.volume,
            }
        )

    if to_store:
        history_collection.insert_many(to_store)

    return len(to_store)


async def _fill_gap_for_symbol(symbol: str) -> int:
    if not await asyncio.to_thread(_history_gap_needs_backfill_sync, symbol):
        return 0

    response = await get_watchlist_chart(symbol, GAP_FILL_RANGE_KEY)
    return await asyncio.to_thread(_persist_gap_fill_history_sync, symbol, response.data)


async def _startup_gap_fill_watchlist_history() -> None:
    symbols = [symbol.symbol for symbol in WATCHLIST_SYMBOLS[:DEFAULT_GAP_FILL_SYMBOLS]]

    for symbol in symbols:
        try:
            await _fill_gap_for_symbol(symbol)
        except Exception:
            logger.exception("Gap-fill history check failed.")


def _live_chart_response_sync(symbol: str, range_key: ChartRange) -> KisChartResponse:
    start_at, _ = _live_chart_window(range_key)
    collection = get_collection(HISTORY_COLLECTION)
    normalized_symbol = symbol.strip().upper()
    documents = list(
        collection.find(
            {
                "symbol": normalized_symbol,
                "stored_at": {"$gte": start_at.replace(tzinfo=None)},
            },
            {"_id": False},
        ).sort("stored_at", ASCENDING)
    )

    if not documents:
        latest = get_collection(LATEST_COLLECTION).find_one(
            {"symbol": normalized_symbol},
            {"_id": False},
        )
        documents = [latest] if latest else []

    return _live_chart_from_documents(normalized_symbol, range_key, documents)


async def get_live_chart_history(symbol: str, range_key: ChartRange) -> KisChartResponse:
    return await asyncio.to_thread(_live_chart_response_sync, symbol, range_key)


async def refresh_market_data() -> KisWatchlistResponse:
    global _last_refresh_response, _last_refresh_started_at, _refresh_lock

    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()

    async with _refresh_lock:
        now = time.monotonic()
        recent_refresh_window = max(
            MIN_REFRESH_SECONDS - 0.5,
            refresh_interval_seconds() - 0.5,
        )

        if (
            _last_refresh_response
            and now - _last_refresh_started_at < recent_refresh_window
        ):
            return _last_refresh_response

        _last_refresh_started_at = now

        response = await _refresh_market_data_unlocked()
        _last_refresh_response = response

        return response


async def _schedule_background_market_refresh() -> None:
    global _last_background_refresh_started_at, _background_refresh_task

    now = time.monotonic()
    if (
        _background_refresh_task
        and not _background_refresh_task.done()
    ):
        return

    if now - _last_background_refresh_started_at < refresh_interval_seconds():
        return

    _last_background_refresh_started_at = now

    async def _runner() -> None:
        try:
            await refresh_market_data()
        except Exception:
            logger.exception("Background market data refresh failed.")

    _background_refresh_task = asyncio.create_task(_runner(), name="market-data-refresh-bg")


async def _refresh_market_data_unlocked() -> KisWatchlistResponse:
    refresh_id = uuid4().hex
    started_at = _utc_now()

    try:
        response = await get_watchlist_quotes(force_refresh=True)
    except KisServiceError as exc:
        completed_at = _utc_now()
        await asyncio.to_thread(
            _record_refresh_error_sync,
            refresh_id,
            started_at,
            completed_at,
            exc,
        )
        raise
    except Exception as exc:
        completed_at = _utc_now()
        await asyncio.to_thread(
            _record_refresh_error_sync,
            refresh_id,
            started_at,
            completed_at,
            exc,
        )
        raise KisServiceError(str(exc)) from exc

    completed_at = _utc_now()
    await asyncio.to_thread(
        _persist_response_sync,
        response,
        refresh_id,
        started_at,
        completed_at,
    )

    return response


async def get_latest_or_refresh_watchlist_quotes() -> KisWatchlistResponse:
    latest_response, newest_stored_at = await asyncio.to_thread(_latest_snapshot_sync)

    if latest_response.count and newest_stored_at:
        age_seconds = (_utc_now() - newest_stored_at).total_seconds()
        if age_seconds <= refresh_interval_seconds() * 2:
            return latest_response

        await _schedule_background_market_refresh()
        return latest_response

    return await refresh_market_data()


async def _scheduler_loop() -> None:
    interval_seconds = refresh_interval_seconds()

    while True:
        loop_started_at = time.monotonic()

        try:
            await refresh_market_data()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Market data refresh failed.")

        elapsed_seconds = time.monotonic() - loop_started_at
        await asyncio.sleep(max(0, interval_seconds - elapsed_seconds))


async def start_market_data_scheduler() -> None:
    global _scheduler_task, _startup_gap_fill_completed

    if startup_gap_fill_enabled() and not _startup_gap_fill_completed:
        await _startup_gap_fill_watchlist_history()
        _startup_gap_fill_completed = True

    if not market_data_scheduler_enabled():
        return

    if _scheduler_task and not _scheduler_task.done():
        return

    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="market-data-refresh")


async def stop_market_data_scheduler() -> None:
    global _background_refresh_task, _scheduler_task

    if _scheduler_task:
        _scheduler_task.cancel()

        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass

        _scheduler_task = None

    if not _background_refresh_task:
        return

    _background_refresh_task.cancel()

    try:
        await _background_refresh_task
    except asyncio.CancelledError:
        pass

    _background_refresh_task = None
