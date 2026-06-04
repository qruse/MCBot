from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

load_dotenv()

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DB_NAME = "mcbot"


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient[dict[str, Any]]:
    return MongoClient(
        os.getenv("MONGO_URI", DEFAULT_MONGO_URI),
        serverSelectionTimeoutMS=int(os.getenv("MONGO_TIMEOUT_MS", "2000")),
    )


def get_database() -> Database[dict[str, Any]]:
    return get_mongo_client()[os.getenv("MONGO_DB_NAME", DEFAULT_MONGO_DB_NAME)]


def get_collection(name: str) -> Collection[dict[str, Any]]:
    return get_database()[name]


def ping_mongo() -> dict[str, str]:
    database_name = os.getenv("MONGO_DB_NAME", DEFAULT_MONGO_DB_NAME)

    try:
        get_mongo_client().admin.command("ping")
    except Exception as exc:
        return {
            "status": "error",
            "database": database_name,
            "message": str(exc),
        }

    return {
        "status": "ok",
        "database": database_name,
        "message": "MongoDB connection is healthy.",
    }
