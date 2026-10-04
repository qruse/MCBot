import pytest
from fastapi.testclient import TestClient

from app.main import app

TOKEN = "test-remote-token"
DASHBOARD = "https://mcbot.qruse.workers.dev"

# No lifespan: the paper service stays unset, so a request that passes every gate gets 503.
local = TestClient(app)
remote = TestClient(app, base_url="https://abc-def.trycloudflare.com")


@pytest.fixture()
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("REMOTE_ACCESS_TOKEN", TOKEN)
    return TOKEN


def auth(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}", "Origin": DASHBOARD}


def test_remote_is_refused_without_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REMOTE_ACCESS_TOKEN", raising=False)

    response = remote.get("/paper/snapshot", headers=auth("anything"))

    assert response.status_code == 403
    assert response.json()["detail"] == "remote_access_disabled"


BAD_AUTH = [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}]


@pytest.mark.parametrize("headers", BAD_AUTH)
def test_remote_requires_matching_bearer_token(token: str, headers: dict[str, str]) -> None:
    response = remote.get("/brokers/toss/prices?symbols=AAPL", headers=headers)

    assert response.status_code == 401


def test_remote_with_token_passes_local_only_paper_checks(token: str) -> None:
    response = remote.get("/paper/snapshot", headers=auth(token))

    assert response.status_code == 503
    assert response.json()["detail"] == "paper_service_unavailable"


def test_remote_commands_still_need_command_header(token: str) -> None:
    response = remote.post("/paper/commands", headers=auth(token), json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "command_header_required"


def test_cloudflare_edge_headers_mark_request_remote(token: str) -> None:
    response = local.get("/paper/snapshot", headers={"Host": "localhost", "CF-Ray": "abc"})

    assert response.status_code == 401


def test_health_is_public_through_tunnel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REMOTE_ACCESS_TOKEN", raising=False)

    assert remote.get("/health").status_code == 200


def test_local_requests_are_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REMOTE_ACCESS_TOKEN", raising=False)

    assert local.get("/paper/snapshot").status_code == 503


def test_cors_headers_cover_rejections_for_dashboard_origin(token: str) -> None:
    response = remote.get("/paper/snapshot", headers={"Origin": DASHBOARD})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == DASHBOARD


def test_cors_rejects_other_workers_sites(token: str) -> None:
    response = remote.get("/health", headers={"Origin": "https://evil.qruse.workers.dev"})

    assert "access-control-allow-origin" not in response.headers
