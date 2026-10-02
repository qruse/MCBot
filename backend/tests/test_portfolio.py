"""Allocation execution invariants with synthetic inputs, never provider requests."""

from copy import deepcopy
from decimal import Decimal as D

import pytest
from test_paper import NOW, command, proposal, start
from test_paper import service as service
from test_strategies import register

from app.paper import domain, portfolio
from app.paper.contracts import AdaptivePortfolioPlan, Proposal
from app.paper.market import demo_snapshot
from app.paper.strategies.contracts import Draft
from app.paper.strategies.runtime import StrategyError, execute, prepare_context

SOURCE = """def decide(c):
    if not c["can_enter"] or not c.get("portfolio"):
        return {}
    symbols = set(c["portfolio"]["target_weights"]) - {"CASH"}
    if not symbols <= set(c["candidate_ready"]):
        return {}
    return {"target_weights": c["portfolio"]["target_weights"], "reason": "Approved allocation."}
"""


def activate(service):
    start(service)
    module = register(
        service,
        Draft(
            strategy_id="test-portfolio",
            version=1,
            protocol_version=3,
            parent_ref="cash-v1@1",
            name="Allocation test",
            hypothesis="Bounded allocation.",
            failure_criterion="Accounting, risk or hourly limit failure.",
            source=SOURCE,
        ),
    )
    value = proposal(
        service,
        schema_version=6,
        playbook_id="test-portfolio",
        max_exposure_percent="65",
        portfolio={
            "target_weights": {
                "005930": "0.2",
                "000660": "0.2",
                "042700": "0.2",
                "114800": "0.0167",
                "123310": "0.0167",
                "145670": "0.0166",
                "CASH": "0.35",
            }
        },
    )
    invalid = Proposal.model_validate(value).model_copy(update={"portfolio": None})
    assert (
        service.validate_proposal(
            invalid, NOW, service.store.current()["session"], service.store.db
        )
        == "portfolio_plan_required"
    )
    with pytest.raises(ValueError):
        Proposal.model_validate({**value, "schema_version": 5})
    assert service.submit(value, value["proposal_id"], NOW)["status"] == "accepted"
    return module


def fill(service):
    service.tick(NOW + 30000, demo_snapshot("KR", NOW + 30000))
    assert not service.store.current()["session"]["fills"]
    service.tick(NOW + 60000, demo_snapshot("KR", NOW + 60000))
    return service.store.current()["session"]


def test_allocation_admission_protocol_and_delayed_whole_share_fills(service):
    activate(service)
    state = fill(service)
    assert len(state["fills"]) == 6
    data = state["latest"]
    nav = portfolio.valuation(state, data, NOW + 60000)[3]
    cash = D(state["cash"])
    assert cash >= nav * D(".35") and nav - cash <= nav * D(".65")
    assert cash + sum(D(f["gross"]) + D(f["fee"]) for f in state["fills"]) == D(state["baseline"])
    assert all(D(f["fee"]) == D(f["gross"]) * D(".00015") for f in state["fills"])
    assert all(p["entrySourceTime"] > NOW + 30000 for p in state["positions"])
    assert len({f["id"] for f in state["fills"]}) == 6
    context = domain.strategy_context(
        state, data, NOW + 60000, domain.candidate_groups(state), [], True
    )
    context = prepare_context(context, 3)
    for source in (
        'def decide(c):\n return {"target_weights": {"CASH": "0.5", "EVIL": "0.5"}}',
        'def decide(c):\n return {"entry_group": next(iter(c["groups"]))}',
    ):
        with pytest.raises(StrategyError):
            execute(source, context)
    legacy = prepare_context(context, 1)
    assert "portfolio" not in legacy and "target_weights" not in execute(
        "def decide(c):\n return {}", legacy
    )


def test_partial_rebalance_hourly_budget_provenance_and_feedback(service):
    module = activate(service)
    state = fill(service)
    old = deepcopy(next(p for p in state["positions"] if p["symbol"] == "005930"))
    state["policy"]["portfolio"]["target_weights"].update({"005930": "0.1", "CASH": "0.45"})
    state["policyVersion"] += 1
    state["policy"]["expires_at"] = NOW + 7200000
    service.store.save({"session": state, "benchmark": service.store.current()["benchmark"]})
    service.tick(NOW + 90000, demo_snapshot("KR", NOW + 90000))
    assert len(service.store.current()["session"]["fills"]) == 6
    next_hour = (NOW // portfolio.HOUR + 1) * portfolio.HOUR + 1000
    service.tick(next_hour, demo_snapshot("KR", next_hour))
    before = service.store.current()["session"]
    before_nav = portfolio.valuation(before, before["latest"], next_hour)[3]
    service.tick(next_hour + 30000, demo_snapshot("KR", next_hour + 30000))
    after = service.store.current()["session"]
    new_fills = after["fills"][6:]
    assert new_fills and sum(D(f["gross"]) for f in new_fills) <= before_nav * D(".2")
    lot = next(p for p in after["positions"] if p["entryId"] == old["entryId"])
    assert 0 < lot["shares"] < old["shares"]
    for key in ("entryPrice", "entrySourceTime", "policyVersion", "strategyRef", "strategyDigest"):
        assert lot[key] == old[key]
    sale = next(f for f in new_fills if f["entryId"] == old["entryId"])
    allocated = D(old["entryCost"]) - D(lot["entryCost"])
    assert D(sale["netProfit"]) == D(sale["gross"]) - D(sale["fee"]) - allocated
    feedback = next(f for f in service.strategies.feedback() if f["strategy_ref"] == module["ref"])
    assert feedback["closed_trades"] == 0  # A partial reduction is not an independent closed trade.
    service.tick(next_hour + 60000, demo_snapshot("KR", next_hour + 60000))
    assert service.store.current()["session"]["fills"] == after["fills"]


@pytest.mark.parametrize("block", ["stale", "expiry", "observer", "entry_pause"])
def test_common_gates_veto_portfolio_execution(service, block):
    activate(service)
    service.tick(NOW + 30000, demo_snapshot("KR", NOW + 30000))
    state = service.store.current()["session"]
    data = demo_snapshot("KR", NOW + 60000)
    cash_status = portfolio.status(state, NOW + 30000)
    assert next(r for r in cash_status["rows"] if r["symbol"] == "CASH")["actualPercent"] == "100"
    if block == "stale":
        data["quotes"]["145670"]["sourceTime"] = NOW - 120000
    elif block == "expiry":
        state["policy"]["expires_at"] = NOW + 40000
    elif block == "observer":
        state["mode"] = "observer"
    else:
        state["entriesPaused"] = True
    domain.ingest(state, data, NOW + 60000, strategy_runner=service.strategies.run)
    assert not state["fills"] and state["cash"] == state["baseline"]


def test_risk_stop_cooldown_survives_policy_and_persistence(service):
    activate(service)
    state = fill(service)
    stop_data = demo_snapshot("KR", NOW + 90000)
    stop_data["quotes"]["005930"]["price"] = "65000"
    service.tick(NOW + 90000, stop_data)
    state = service.store.current()["session"]
    assert state["fills"][-1]["reason"] == "position_stop"
    assert state["portfolioRuntime"]["risk_blocks"]["005930"] == NOW + 3690000
    now = (NOW // portfolio.HOUR + 1) * portfolio.HOUR + 1000
    data = demo_snapshot("KR", now)
    state["policy"]["expires_at"] = NOW + 7200000
    assert not any(
        o["symbol"] == "005930" and o["side"] == "buy" for o in portfolio.orders(state, data, now)
    )
    assert state["portfolioRuntime"] == service.store.current()["session"]["portfolioRuntime"]


def activate_adaptive(service):
    start(service)
    module = register(
        service,
        Draft(
            strategy_id="test-flexible",
            version=1,
            protocol_version=4,
            parent_ref="cash-v1@1",
            name="Adaptive test",
            hypothesis="Explicit active weights and rotations.",
            failure_criterion="Unapproved liquidation or scope changes.",
            source=SOURCE,
        ),
    )
    value = proposal(
        service,
        schema_version=7,
        playbook_id="test-flexible",
        max_exposure_percent="65",
        portfolio={
            "mode": "adaptive",
            "target_weights": {
                "005930": "0.25",
                "000660": "0.25",
                "042700": "0.10",
                "114800": "0.025",
                "123310": "0.025",
                "145670": "0",
                "CASH": "0.35",
            },
        },
    )
    parsed = Proposal.model_validate(value)
    assert isinstance(parsed.portfolio, AdaptivePortfolioPlan)
    with pytest.raises(ValueError):
        Proposal.model_validate({**value, "schema_version": 6})
    assert service.submit(value, value["proposal_id"], NOW)["status"] == "accepted"
    return module


def test_adaptive_zero_weights_are_versioned_and_preserve_pinned_monitoring(service):
    module = activate_adaptive(service)
    state = fill(service)
    assert len(state["positions"]) == 5
    assert "145670" in domain.candidate_symbols(state)
    assert not any(f["symbol"] == "145670" for f in state["fills"])
    context = domain.strategy_context(
        state, state["latest"], NOW + 60000, domain.candidate_groups(state), [], True
    )
    assert service.strategies.run(module["ref"], context)["target_weights"]["145670"] == "0"
    with pytest.raises(StrategyError):
        execute(SOURCE, prepare_context(context, 3))


def test_explicit_theme_retirement_is_admitted_and_reduces_original_lot(service):
    activate_adaptive(service)
    fill(service)
    original = service.store.current()["session"]
    old = deepcopy(next(p for p in original["positions"] if p["symbol"] == "005930"))
    now = NOW + portfolio.HOUR + 1000
    value = proposal(
        service,
        now,
        schema_version=7,
        playbook_id="test-flexible",
        max_exposure_percent="65",
        portfolio={
            "mode": "adaptive",
            "target_weights": {
                "111111": "0.25",
                "000660": "0.25",
                "042700": "0.10",
                "005930": "0",
                "114800": "0.025",
                "123310": "0.025",
                "145670": "0",
                "CASH": "0.35",
            },
            "retirements": [
                {
                    "symbol": "005930",
                    "name": "Synthetic old thesis",
                    "rationale": "Fixture thesis invalidation.",
                    "evidence_ids": ["fixture-evidence"],
                }
            ],
        },
    )
    value["allowed_symbols"][0] = "111111"
    value["candidate_groups"][0]["candidates"][0]["symbol"] = "111111"
    value["evidence"][0]["evidence_id"] = "rotation-evidence"
    for group in value["candidate_groups"]:
        for candidate in group["candidates"]:
            candidate["evidence_ids"] = ["rotation-evidence"]
    value["portfolio"]["retirements"][0]["evidence_ids"] = ["rotation-evidence"]
    parsed = Proposal.model_validate(value)
    for retirement, reason in (
        ([], "invalid_retirements"),
        (
            [{**value["portfolio"]["retirements"][0], "evidence_ids": ["missing-evidence"]}],
            "invalid_retirement_evidence",
        ),
    ):
        invalid = parsed.model_copy(
            update={
                "portfolio": parsed.portfolio.model_copy(
                    update={
                        "retirements": [
                            type(parsed.portfolio.retirements[0]).model_validate(r)
                            for r in retirement
                        ]
                    }
                )
            }
        )
        assert service.validate_proposal(invalid, now, original, service.store.db) == reason
    assert service.submit(value, value["proposal_id"], now)["status"] == "accepted"
    before_count = len(original["fills"])
    for offset in (30000, 60000):
        data = demo_snapshot("KR", now + offset)
        for field in ("quotes", "minute", "daily", "securities"):
            data[field]["111111"] = deepcopy(data[field]["005930"])
        service.tick(now + offset, data)
    state = service.store.current()["session"]
    trades = state["fills"][before_count:]
    assert trades and all(f["side"] == "sell" for f in trades)
    assert all(f["reason"] == "portfolio_rotation" for f in trades)
    lot = next(p for p in state["positions"] if p["entryId"] == old["entryId"])
    assert 0 < lot["shares"] < old["shares"]
    assert lot["strategyDigest"] == old["strategyDigest"] and lot["entryPrice"] == old["entryPrice"]
    assert state["portfolioRuntime"]["risk_blocks"]["005930"] == now + 60000 + portfolio.HOUR
    assert sum(D(f["gross"]) for f in trades) <= D(state["config"]["capital"]) * D(".2")


def test_zero_cash_target_keeps_fee_funding_and_legacy_rejection(service):
    start(service)
    register(
        service,
        Draft(
            strategy_id="test-zero-cash",
            version=1,
            protocol_version=4,
            parent_ref="cash-v1@1",
            name="Zero cash test",
            hypothesis="Zero cash targets preserve fee-aware whole-share funding.",
            failure_criterion="Negative cash, borrowing or changed legacy target semantics.",
            source=SOURCE,
        ),
    )
    value = proposal(
        service,
        schema_version=7,
        playbook_id="test-zero-cash",
        max_exposure_percent="100",
        portfolio={
            "mode": "adaptive",
            "target_weights": {
                "005930": "1",
                "114800": "0",
                "123310": "0",
                "145670": "0",
                "CASH": "0",
            },
        },
    )
    value["allowed_symbols"] = ["005930"]
    value["candidate_groups"][0]["candidates"] = value["candidate_groups"][0]["candidates"][:1]
    legacy = {
        **value,
        "schema_version": 6,
        "portfolio": {"target_weights": value["portfolio"]["target_weights"]},
    }
    with pytest.raises(ValueError):
        Proposal.model_validate(legacy)
    assert service.submit(value, value["proposal_id"], NOW)["status"] == "accepted"
    state = fill(service)
    assert len(state["fills"]) == 1 and state["fills"][0]["symbol"] == "005930"
    buy = state["fills"][0]
    assert D(state["cash"]) == D(state["baseline"]) - D(buy["gross"]) - D(buy["fee"])
    assert 0 <= D(state["cash"]) < D(buy["priceKrw"]) * D("1.00015")
    assert D(buy["fee"]) == D(buy["gross"]) * D(".00015")


def test_adaptive_general_etf_blocks_entries_but_keeps_inverse_monitoring(service):
    activate_adaptive(service)
    data = demo_snapshot("KR", NOW + 30000)
    data["securities"]["005930"]["securityType"] = "ETF"
    service.tick(NOW + 30000, data)
    state = service.store.current()["session"]
    assert state["candidateChecks"]["005930"] == "general_etf_excluded"
    assert state["candidateChecks"]["114800"] is None
    assert not state["fills"] and state["cash"] == state["baseline"]


def test_owner_continuous_mode_waits_flat_without_automatic_resume(service):
    start(service)
    command(service, "enable_continuous")
    before = deepcopy(service.store.current()["session"])
    close = NOW + 3600000
    opened = demo_snapshot("KR", NOW + 30000)
    opened["marketClose"] = close
    service.tick(NOW + 30000, opened)
    assert service.store.current()["session"]["leaseUntil"] > close
    closed = demo_snapshot("KR", close)
    closed.update(marketOpen=False, marketClose=close)
    service.tick(close, closed)
    state = service.store.current()["session"]
    assert state["lifecycle"] == "running" and state["leaseUntil"] >= close + 86400000
    for key in ("id", "cash", "baseline", "fills", "positions", "policy"):
        assert state[key] == before[key]
    command(service, "pause", now=close + 1000)
    service.tick(close + 90000000, closed)
    assert service.store.current()["session"]["lifecycle"] == "paused"


def test_continuous_mode_refuses_unfinished_closing_holdings(service):
    activate(service)
    fill(service)
    command(service, "enable_continuous", now=NOW + 61000)
    opened = demo_snapshot("KR", NOW + 90000)
    opened["marketClose"] = NOW + 3600000
    service.tick(NOW + 90000, opened)
    closed = demo_snapshot("KR", NOW + 3600000)
    closed.update(marketOpen=False, marketClose=NOW + 3600000)
    service.tick(NOW + 3600000, closed)
    state = service.store.current()["session"]
    assert state["positions"] and state["lifecycle"] == "paused"
    assert state["gaps"][-1]["reason"] == "closing_exit_incomplete"


@pytest.mark.parametrize("market,lead", [("KR", 720000), ("US", 300000)])
def test_closing_window_exits_fresh_positions_and_blocks_entries(service, market, lead):
    from app.paper.market import calendar_state

    if market == "KR":
        activate(service)
        fill(service)
    else:
        start(service, market="US")
        value = proposal(service)
        assert service.submit(value, value["proposal_id"], NOW)["status"] == "accepted"
        for offset in (30000, 60000):
            service.tick(NOW + offset, demo_snapshot("US", NOW + offset))
    original = deepcopy(service.store.current()["session"])
    assert original["positions"]
    entry_count = len(original["fills"])
    now = NOW + 120000
    calendar = {"data": {"today": {
        "date": "2026-09-30",
        "regularMarket": {
            "startTime": "2026-09-30T01:00:00Z",
            "endTime": "2026-09-30T06:30:00Z",
        },
    }}}
    if market == "KR":
        calendar["data"]["today"]["integrated"] = {
            "regularMarket": calendar["data"]["today"]["regularMarket"]
        }
    close = 1790749800000
    assert not calendar_state(calendar, market, close - lead - 1)["closingSoon"]
    assert calendar_state(calendar, market, close - lead)["closingSoon"]
    # Test the engine boundary independently of collector closingSoon.
    fresh = demo_snapshot(market, now)
    fresh.update(marketClose=now + lead, closingSoon=False)
    stale = deepcopy(fresh)
    for quote in stale["quotes"].values():
        quote["sourceTime"] = now - 90001
    blocked = deepcopy(original)
    domain.ingest(blocked, stale, now)
    assert blocked["fills"] == original["fills"] and blocked["positions"]
    domain.ingest(original, fresh, now)
    assert not original["positions"] and original["pending"] is None
    assert all(f["reason"] == "closing_exit" for f in original["fills"][entry_count:])
    exit_count = len(original["fills"])
    following = demo_snapshot(market, now + 30000)
    following.update(marketClose=now + lead, closingSoon=False)
    domain.ingest(original, following, now + 30000)
    assert len(original["fills"]) == exit_count
    assert not original["positions"] and original["pending"] is None
