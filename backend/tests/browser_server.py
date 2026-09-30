"""Disposable, broker-free backend used only by the browser smoke tests."""

import os
import sys
import tempfile
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mcbot-browser-") as directory:
        os.environ["PAPER_DB_PATH"] = str(Path(directory) / "test.db")
        os.environ["PAPER_EXCHANGE_PATH"] = str(Path(directory) / "exchange")
        os.environ["MARKET_DATA_PROVIDER"] = "toss"
        os.environ["TOSS_CLIENT_ID"] = ""
        os.environ["TOSS_CLIENT_SECRET"] = ""
        os.chdir(Path(__file__).resolve().parents[1])
        sys.path.insert(0, str(Path.cwd()))
        from app.main import app

        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8011))

        @app.post("/__test__/shutdown")
        async def shutdown():
            server.should_exit = True
            return {"stopping": True}

        server.run()
