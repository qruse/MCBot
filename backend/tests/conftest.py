"""All API regression tests have isolated storage and no background brokerage collection."""

import pytest


@pytest.fixture(autouse=True)
def isolated_paper_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DB_PATH", str(tmp_path / "paper.sqlite3"))
    monkeypatch.setenv("PAPER_EXCHANGE_PATH", str(tmp_path / "exchange"))
    monkeypatch.setenv("PAPER_BACKGROUND_ENABLED", "false")
