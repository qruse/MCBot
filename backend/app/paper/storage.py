"""Single-writer SQLite transactions; raw observations and history are never truncated."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO migrations VALUES(1);
            CREATE TABLE IF NOT EXISTS sessions(
                id TEXT PRIMARY KEY, active INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active ON sessions(active) WHERE active=1;
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, request TEXT, receipt TEXT);
            CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS samples(
                session_id TEXT, lane TEXT, timestamp INTEGER, payload TEXT,
                PRIMARY KEY(session_id,lane,timestamp));
            CREATE TABLE IF NOT EXISTS exports(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(
                id TEXT PRIMARY KEY, session_id TEXT, slot INTEGER, started INTEGER,
                deadline INTEGER, completed INTEGER, UNIQUE(session_id,slot));
            CREATE TABLE IF NOT EXISTS proposals(
                id TEXT PRIMARY KEY, digest TEXT, payload TEXT, receipt TEXT);
            CREATE TABLE IF NOT EXISTS experiments(
                id TEXT PRIMARY KEY, session_id TEXT, registered INTEGER,
                payload TEXT, status TEXT NOT NULL DEFAULT 'hypothesis');
        """)

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def current(self):
        row = self.db.execute("SELECT payload FROM sessions WHERE active=1").fetchone()
        return json.loads(row[0]) if row else None

    def save(self, bundle):
        for lane in ("session", "benchmark"):
            state = bundle[lane]
            for point in state["samples"]:
                self.db.execute(
                    "INSERT OR IGNORE INTO samples VALUES(?,?,?,?)",
                    (bundle["session"]["id"], lane, point["timestamp"], encode(point)),
                )
            # Keep only the newest sample in the state; chart queries raw samples separately.
            state["samples"] = state["samples"][-1:]
        self.db.execute(
            "INSERT INTO sessions VALUES(?,1,?) ON CONFLICT(id) DO UPDATE "
            "SET payload=excluded.payload",
            (bundle["session"]["id"], encode(bundle)),
        )

    def samples(self, session_id, lane="session", limit=1000):
        rows = self.db.execute(
            "SELECT payload FROM samples WHERE session_id=? AND lane=? "
            "ORDER BY timestamp DESC LIMIT ?",
            (session_id, lane, limit),
        )
        return [json.loads(row[0]) for row in rows][::-1]
