"""Paper strategy registration, source provenance, execution, replay and rollback."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_paper import NOW, proposal, start
from test_paper import service as service

from app.main import app
from app.paper import domain
from app.paper.market import demo_snapshot
from app.paper.service import Conflict, PaperService
from app.paper.strategies.contracts import Draft, Rollback
from app.paper.strategies.evaluation import replay
from app.paper.strategies.registry import check_draft, scenarios
from app.paper.strategies.runtime import StrategyError, execute

SOURCE = """def decide(context):
    if not context["can_enter"]:
        return {}
    group = next((g for g in context["groups"] if g.endswith("-semis")), None)
    if group is None:
        return {}
    symbol = context["groups"][group][0]
    return {"entry_group": group, "weights": {symbol: "1"}, "reason": "Test single allocation."}
"""


def draft(version=1, source=SOURCE):
    return Draft(
        strategy_id="test-allocation",
        version=version,
        parent_ref="theme-top3-v1@1" if version == 1 else "test-allocation@1",
        name="Test allocation",
        hypothesis="Synthetic allocation contract test.",
        failure_criterion="Any risk or accounting invariant violation.",
        source=source,
    )


def register(service, candidate):
    report = check_draft(candidate)
    assert report["passed"], report
    service.strategies.record(report, NOW)
    return service.strategies.register(candidate, report["id"], NOW)


def test_registration_binds_exact_source_and_versions_are_immutable(service):
    candidate = draft()
    with pytest.raises(StrategyError, match="strategy_checks_required"):
        service.strategies.register(candidate, "missing", NOW)
    report = service.strategies.record(check_draft(candidate), NOW)
    changed = candidate.model_copy(update={"source": SOURCE + "\n# changed"})
    with pytest.raises(StrategyError, match="strategy_checks_required"):
        service.strategies.register(changed, report["id"], NOW)
    item = service.strategies.register(candidate, report["id"], NOW)
    assert item["digest"] and item["ref"] == "test-allocation@1"
    assert service.strategies.register(candidate, report["id"], NOW) == item
    with pytest.raises(StrategyError, match="strategy_version_immutable"):
        service.strategies.register(changed, report["id"], NOW)


def test_registered_code_executes_with_pinned_versions_and_hard_stops(service):
    register(service, draft())
    second = register(service, draft(2, SOURCE + "\n# second revision"))
    start(service)
    p = proposal(service, playbook_id="test-allocation", strategy_version=2)
    assert service.submit(p, p["proposal_id"], NOW)["status"] == "accepted"
    for now in (NOW + 30000, NOW + 60000):
        service.tick(now, demo_snapshot("KR", now))
    s = service.store.current()["session"]
    assert len(s["positions"]) == 1
    assert s["positions"][0]["strategyRef"] == "test-allocation@2"
    assert s["positions"][0]["strategyDigest"] == second["digest"]
    rollback = Rollback(
        command_id="rollback",
        session_id=s["id"],
        expected_policy_version=1,
        target_ref="test-allocation@1",
        reason="Synthetic rollback check.",
    )
    result = service.rollback_strategy(rollback, NOW + 61000)
    assert result == service.rollback_strategy(rollback, NOW + 62000)
    s = service.store.current()["session"]
    assert s["policy"]["strategy_version"] == 1
    assert s["positions"][0]["strategyRef"] == "test-allocation@2"
    with pytest.raises(Conflict, match="policy_version_conflict"):
        service.rollback_strategy(rollback.model_copy(update={"command_id": "stale"}), NOW + 62000)
    data = demo_snapshot("KR", NOW + 90000)
    data["quotes"]["005930"]["price"] = "69000"
    data["minute"] = {}
    service.tick(NOW + 90000, data)
    s = service.store.current()["session"]
    assert s["fills"][-1]["reason"] == "position_stop"
    assert s["fills"][-1]["strategyRef"] == "test-allocation@2"
    feedback = service.strategies.feedback()[0]
    assert feedback["source"] == "demo" and feedback["closed_trades"] == 1
    assert feedback["strategy_ref"] == "test-allocation@2"
    original = deepcopy(s)
    state, inputs, modules = service.replay_inputs("test-allocation@1", s["id"])
    report = replay(state, inputs, modules, "test-allocation@1")
    assert report["input_count"] > 0 and not report["profitability_validated"]
    assert len(report["results"]) == 2
    assert service.store.current()["session"] == original
    reopened = PaperService(
        service.store.db.execute("PRAGMA database_list").fetchone()[2], service.exchange
    )
    try:
        assert reopened.strategies.get("test-allocation@2")["digest"] == second["digest"]
    finally:
        reopened.store.db.close()


@pytest.mark.parametrize(
    "source,reason",
    [
        ('def decide(c):\n    return {"cash": "1000000000"}', "invalid_strategy_output"),
        ('def decide(c):\n    return {"entry_group":"unknown"}', "invalid_strategy_output"),
        (
            'def decide(c):\n    return {"exits":{"unknown":"strategy_exit"}}',
            "invalid_strategy_output",
        ),
        ("def decide(c):\n    while True: pass", "strategy_timeout"),
        (
            'def decide(c):\n    g = next(iter(c["groups"]))\n'
            '    return {"entry_group": g, "weights": {c["groups"][g][0]: "0.5"}}',
            "invalid_strategy_output",
        ),
    ],
)
def test_worker_rejects_invalid_intents_and_times_out(source, reason, monkeypatch):
    monkeypatch.setattr("app.paper.strategies.runtime.TIMEOUT_SECONDS", 0.5)
    with pytest.raises(StrategyError, match=reason):
        execute(source, scenarios()[0][1])


def test_worker_does_not_inherit_credentials(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "dummy-test-only")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-only")
    source = (
        "import os\ndef decide(c):\n"
        '    assert "TOSS_CLIENT_SECRET" not in os.environ\n'
        '    assert "OPENAI_API_KEY" not in os.environ\n'
        "    return {}\n"
    )
    assert execute(source, scenarios()[0][1])["entry_group"] is None


def test_module_failure_cannot_prevent_price_risk_exit(service):
    from test_paper import activate

    start(service)
    activate(service)
    s = service.store.current()["session"]
    data = demo_snapshot("KR", NOW + 90000)
    data["quotes"]["005930"]["price"] = "69000"

    def fail(*args):
        raise StrategyError("strategy_timeout")

    domain.ingest(s, data, NOW + 90000, strategy_runner=fail)
    assert s["fills"][-1]["reason"] == "position_stop"
    assert s["strategyError"] and s["pending"] is None


def test_unknown_strategy_rejected_and_api_registration_does_not_activate(service):
    start(service)
    p = proposal(service, playbook_id="not-registered")
    assert service.submit(p, p["proposal_id"], NOW)["reason"] == "strategy_not_registered"
    with TestClient(app) as client:
        headers = {"X-MCBot-Command": "local-paper"}
        body = draft().model_dump(mode="json")
        assert client.post("/paper/strategies/validate", json=body).status_code == 403
        report = client.post("/paper/strategies/validate", json=body, headers=headers).json()
        assert report["passed"]
        response = client.post(
            "/paper/strategies/register",
            json={"draft": body, "evaluation_id": report["id"]},
            headers=headers,
        )
        assert response.status_code == 200
        snapshot = client.get("/paper/snapshot").json()
        assert snapshot["session"]["lifecycle"] == "idle"
        assert snapshot["session"]["policy"] is None
        assert any(m["ref"] == "test-allocation@1" for m in snapshot["research"]["strategies"])
