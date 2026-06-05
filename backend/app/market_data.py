from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.database import get_collection
from app.kis import (
    WATCHLIST_SYMBOLS,
    KisQuote,
    KisServiceError,
    KisWatchlistResponse,
    _kis_environment,
    get_watchlist_quotes,
)

DEFAULT_REFRESH_SECONDS = 10
LATEST_COLLECTION = "market_quote_latest"
HISTORY_COLLECTION = "market_quote_history"
RUNS_COLLECTION = "market_refresh_runs"

_scheduler_task: asyncio.Task[None] | None = None
_refresh_lock: asyncio.Lock | None = None
_last_refresh_started_at = 0.0
_last_refresh_response: KisWatchlistResponse | None = None
_indexes_ready = False
logger = logging.getLogger(__name__)


def refresh_interval_seconds() -> int:
    raw_value = os.getenv("MARKET_DATA_REFRESH_SECONDS", str(DEFAULT_REFRESH_SECONDS)).strip()

    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_REFRESH_SECONDS


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


async def refresh_market_data() -> KisWatchlistResponse:
    global _last_refresh_response, _last_refresh_started_at, _refresh_lock

    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()

    async with _refresh_lock:
        now = time.monotonic()
        recent_refresh_window = max(1.0, refresh_interval_seconds() - 0.5)

        if (
            _last_refresh_response
            and now - _last_refresh_started_at < recent_refresh_window
        ):
            return _last_refresh_response

        _last_refresh_started_at = now

        response = await _refresh_market_data_unlocked()
        _last_refresh_response = response

        return response


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

    if latest_response.count:
        try:
            return await refresh_market_data()
        except Exception:
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
    global _scheduler_task

    if _scheduler_task and not _scheduler_task.done():
        return

    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="market-data-refresh")


async def stop_market_data_scheduler() -> None:
    global _scheduler_task

    if not _scheduler_task:
        return

    _scheduler_task.cancel()

    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass

    _scheduler_task = None
