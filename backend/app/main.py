import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import ping_mongo
from app.kis import KisServiceError, KisWatchlistResponse
from app.market_data import (
    get_latest_or_refresh_watchlist_quotes,
    start_market_data_scheduler,
    stop_market_data_scheduler,
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: dict[str, str]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
