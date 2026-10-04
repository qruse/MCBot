import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


app = FastAPI(
    title="MCBot Backend",
    description="Money Copy Bot API",
    version="0.1.0",
    root_path=os.getenv("ROOT_PATH", ""),
)

LOCAL_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# Comma-separated extra origins, e.g. a custom domain for the deployed dashboard.
EXTRA_ORIGINS = [
    origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()
]

# The Cloudflare Workers dashboard (mcbot.<account>.workers.dev) and its preview URLs.
WORKERS_ORIGIN_REGEX = r"^https://([a-z0-9-]+-)?mcbot\.[a-z0-9-]+\.workers\.dev$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS + EXTRA_ORIGINS,
    allow_origin_regex=WORKERS_ORIGIN_REGEX,
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
    return HealthResponse(
        status="ok",
        service="mcbot-backend",
        version=app.version,
    )
