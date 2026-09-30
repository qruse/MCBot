import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import ping_mongo
from app.kis import (
    ChartRange,
    KisChartResponse,
    KisServiceError,
    KisWatchlistResponse,
    get_watchlist_chart,
)
from app.market_data import (
    get_latest_or_refresh_watchlist_quotes,
    get_live_chart_history,
    start_market_data_scheduler,
    stop_market_data_scheduler,
)
from app.toss import router as toss_router
from app.universe import ThemeUniverseResponse, get_theme_universe


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: dict[str, str]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if os.getenv("MARKET_DATA_PROVIDER", "toss") == "kis":
        await start_market_data_scheduler()

    try:
        yield
    finally:
        await stop_market_data_scheduler()


app = FastAPI(
    title="MCBot Backend",
    description="Money Copy Bot API",
    version="0.1.0",
    root_path=os.getenv("ROOT_PATH", ""),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(toss_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": "Money Copy Bot backend is running.",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    database = ping_mongo()

    return HealthResponse(
        status="ok" if database["status"] == "ok" else "degraded",
        service="mcbot-backend",
        version=app.version,
        database=database,
    )


@app.get("/quotes/kis/watchlist", response_model=KisWatchlistResponse)
async def read_kis_watchlist_quotes() -> KisWatchlistResponse:
    try:
        return await get_latest_or_refresh_watchlist_quotes()
    except KisServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@app.get("/quotes/kis/history/{symbol}", response_model=KisChartResponse)
async def read_kis_watchlist_history(
    symbol: str,
    range_key: Annotated[ChartRange, Query(alias="range")] = "LIVE",
) -> KisChartResponse:
    try:
        if range_key == "LIVE":
            return await get_live_chart_history(symbol, range_key)

        if range_key == "1D":
            live_history = await get_live_chart_history(symbol, range_key)
            if live_history.count >= 12:
                return live_history

            downloaded_history = await get_watchlist_chart(symbol, range_key)
            return downloaded_history.model_copy(
                update={"errors": [*live_history.errors, *downloaded_history.errors]}
            )

        return await get_watchlist_chart(symbol, range_key)
    except KisServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@app.get("/universe/themes", response_model=ThemeUniverseResponse)
def read_theme_universe(
    mode: Annotated[Literal["core", "all"], Query()] = "core",
    include_extended: Annotated[bool, Query()] = False,
) -> ThemeUniverseResponse:
    return get_theme_universe(mode=mode, include_extended=include_extended)
