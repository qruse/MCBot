import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import ping_mongo


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: dict[str, str]


app = FastAPI(
    title="MCBot Backend",
    description="Money Copy Bot API",
    version="0.1.0",
    root_path=os.getenv("ROOT_PATH", ""),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
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
