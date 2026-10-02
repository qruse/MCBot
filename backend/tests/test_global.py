"""Shared native cash, calendar/risk isolation and immutable migration; no provider quota."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from test_paper import NOW, command
from test_paper import service as service
from test_strategies import register

from app import toss
from app.paper import domain
from app.paper import global_account as global_book
from app.paper.contracts import Command, Proposal, Settings
from app.paper.market import Collector, GlobalCollector, demo_snapshot
from app.paper.service import Conflict
from app.paper.strategies.contracts import Draft

SOURCE = '''def decide(c):
    if not c["can_enter"] or not c.get("portfolio"):
        return {}
    if not set(c.get("active_candidates", [])) <= set(c["candidate_ready"]):
        return {}
    return {"target_weights": c["portfolio"]["target_weights"], "reason": "Global targets."}
'''


def data(now, kr=True, us=True):
    markets = {m: demo_snapshot(m, now) for m in ("KR", "US")}
    for m, opened in (("KR", kr), ("US", us)):
        markets[m]["marketOpen"] = opened
        markets[m]["id"] += str(opened)
    return global_book.combine(markets, now, markets["US"]["fx"])


def activate(service, cash="0.4"):
    command(service, "new", settings=Settings(market="GLOBAL", capital="10000000",
                                             source="demo", mode="adaptive"))
    command(service, "start")
    service.tick(NOW, data(NOW))
    register(service, Draft(strategy_id="test-global", version=1, protocol_version=5,
                           parent_ref="cash-v1@1", name="Global test",
                           hypothesis="One conserved global capital.",
                           failure_criterion="Any cash, cost, freshness or risk breach.",
                           source=SOURCE))
    # The legacy helper creates its native candidate list; build the new global contract explicitly.
    service.claim("global-test-run", NOW)
    manifest = __import__("json").loads((service.exchange / "latest.json").read_text())
    state = service.store.current()["session"]
    stock = (D(1) - D(cash) - D('0.00000006')) / 2
    extra = [('KR', '000660'), ('KR', '042700'), ('US', 'AVGO')]
    value = {
        "schema_version": 8, "proposal_id": "global-test-plan", "run_id": "global-test-run",
        "session_id": state["id"], "snapshot_id": manifest["snapshot_id"], "market": "GLOBAL",
        "base_policy_version": 0, "as_of": NOW, "valid_from": NOW, "expires_at": NOW + 3600000,
        "playbook_id": "test-global",
        "allowed_symbols": ["KR:005930", "US:NVDA", *[f'{m}:{v}' for m, v in extra]],
        "candidate_groups": [{"group_id": f'{m.lower()}-{symbol}', "name": "Synthetic stock theme",
                              "candidates": [{"market": m, "symbol": symbol, "name": symbol,
                                              "rationale": "Fixture only.",
                                              "evidence_ids": ["global-fixture"]}]}
                             for m, symbol in (("KR", "005930"), ("US", "NVDA"), *extra)],
        "inverse_groups": [{"group_id": "selected-inverse", "name": "Index inverses",
                            "candidates": [{"market": "US", "symbol": symbol, "name": symbol,
                                            "rationale": "Fixture only.",
                                            "evidence_ids": [symbol]}
                                           for symbol in ('SH', 'PSQ')]}],
        "hypothesis": "Synthetic global cash conservation.", "counterevidence": "No market edge.",
        "rationale": "Fixture only.", "evidence": [{"evidence_id": "global-fixture",
            "source_url": "https://example.com/fixture", "publisher": "Synthetic",
            "published_at": NOW - 1000, "retrieved_at": NOW, "claim": "Fixture only.",
            "excerpt": "", "uncertainty": "No real-market evidence."},
            *[{"evidence_id": symbol,
               "source_url": f'https://www.proshares.com/our-etfs/leveraged-and-inverse/{symbol.lower()}',
               "publisher": "Fixture", "published_at": NOW-1000, "retrieved_at": NOW,
               "claim": "Fixture only.", "excerpt": "", "uncertainty": "No market evidence."}
              for symbol in ('SH', 'PSQ')]],
        "portfolio": {"mode": "adaptive", "retirements": [], "target_weights": {
            "KR:005930": str(stock), "US:NVDA": str(stock), "CASH": cash,
            **{f'{m}:{v}': '0.00000002' for m, v in extra},
            'US:SH': '0', 'US:PSQ': '0'}},
    }
    receipt = service.submit(value, "global-test-plan", NOW)
    assert receipt["status"] == "accepted", receipt
    return value


def fill(service, kr=True, us=True):
    for offset in (30000, 60000):
        service.tick(NOW + offset, data(NOW + offset, kr, us))
    return service.store.current()["session"]


def test_shared_capital_native_fees_fx_and_cash_zero(service):
    activate(service, "0")
    state = fill(service)
    assert {p["market"] for p in state["positions"]} == {"KR", "US"}
    assert len(state["fills"]) == 2 and len(state["fxConversions"]) == 1
    assert all(D(v) >= 0 for v in state["cashBalances"].values())
    for trade in state["fills"]:
        assert D(trade["fee"]) == D(trade["gross"]) * domain.fee(trade["market"])
        assert D(trade["nativePrice"]) * D(trade["fx"]) == D(trade["priceKrw"])
    assert D(state["cash"]) + sum(D(p["entryCost"]) for p in state["positions"]) == D(
        state["baseline"])
    before = deepcopy(state["fills"])
    service.tick(NOW + 90000, data(NOW + 90000))
    assert service.store.current()["session"]["fills"] == before


@pytest.mark.parametrize("kr,us,market", [(True, False, "KR"), (False, True, "US")])
def test_closed_market_never_fills_or_blocks_open_market(service, kr, us, market):
    activate(service)
    state = fill(service, kr, us)
    assert len(state["fills"]) == 1 and state["fills"][0]["market"] == market
    assert state["condition"] == "ready"
    closed = "US" if market == "KR" else "KR"
    assert all(v == "market_closed" for k, v in state["candidateChecks"].items()
               if k.startswith(closed + ":"))


def test_closed_holdings_valuation_ages_but_cannot_sell(service):
    activate(service)
    state = fill(service)
    now = NOW + 120000
    closed = data(now, kr=False, us=True)
    closed["markets"]["KR"]["quotes"] = {}
    closed["quotes"] = {k: v for k, v in closed["quotes"].items() if k.startswith("US:")}
    service.tick(now, closed)
    state = service.store.current()["session"]
    assert global_book.equity(state, closed, now) is not None
    kr_lot = next(p for p in state["positions"] if p["market"] == "KR")
    assert not domain.sell(state, kr_lot, closed, now, "position_stop")
    marks = state["globalStatus"]["holdings"]
    assert next(v for v in marks if v["market"] == "KR")["ageMs"] >= 60000
    assert not service.view()["research"]["paired"]


@pytest.mark.parametrize("failure", ["price", "fx", "history", "metadata"])
def test_stale_open_market_inputs_block_entries(service, failure):
    activate(service)
    broken = data(NOW + 30000)
    if failure == "price":
        broken["markets"]["US"]["quotes"]["NVDA"]["sourceTime"] = NOW - 90001
    elif failure == "fx":
        broken["fx"]["validUntil"] = NOW
    elif failure == "history":
        broken["markets"]["US"]["minute"] = {}
    else:
        broken["markets"]["US"]["securities"]["NVDA"]["status"] = "SUSPENDED"
    for now in (NOW + 30000, NOW + 60000):
        broken["id"] += str(now)
        broken["observedAt"] = now
        service.tick(now, broken)
    assert not service.store.current()["session"]["fills"]


def test_us_sale_keeps_usd_and_kr_purchase_converts_only_needed_cash(service):
    activate(service)
    state = fill(service)
    us_lot = next(p for p in state["positions"] if p["market"] == "US")
    now = NOW + 120000
    snapshot = data(now)
    before = D(state["cashBalances"]["KRW"])
    assert domain.sell(state, us_lot, snapshot, now, "portfolio_rebalance")
    assert D(state["cashBalances"]["KRW"]) == before and D(state["cashBalances"]["USD"]) > 0
    total = global_book.cash_value(state, now)
    assert global_book.fund(state, "KRW", total, snapshot, now)
    assert abs(D(state["cashBalances"]["USD"])) < D("1e-20")
    assert D(state["cashBalances"]["KRW"]) == total
    assert not global_book.fund(state, "KRW", total + 1, snapshot, now)


def test_global_sidecar_liquidates_open_market_then_closed_market_at_fresh_open(service):
    activate(service)
    state = fill(service)
    now = NOW + 120000
    snapshot = data(now, kr=False, us=True)
    for market in ("KR", "US"):
        for quote in snapshot["markets"][market]["quotes"].values():
            quote["price"] = str(D(quote["price"]) * D(".85"))
    snapshot = global_book.combine(snapshot["markets"], now, snapshot["fx"])
    service.tick(now, snapshot)
    state = service.store.current()["session"]
    assert state["sidecarPending"] and state["entriesPaused"]
    assert {p["market"] for p in state["positions"]} == {"KR"}
    assert state["lifecycle"] == "running"
    service.tick(now + 30000, data(now + 30000))
    state = service.store.current()["session"]
    assert state["lifecycle"] == "halted" and not state["positions"]
    assert all(f["reason"] == "sidecar_halt" for f in state["fills"][2:])


def test_native_closing_window_does_not_close_other_market(service):
    activate(service)
    fill(service)
    now = NOW + 120000
    snapshot = data(now)
    snapshot["markets"]["KR"]["marketClose"] = now + 720000
    service.tick(now, snapshot)
    state = service.store.current()["session"]
    assert {p["market"] for p in state["positions"]} == {"US"}
    assert state["fills"][-1]["reason"] == "closing_exit"
    assert state["fills"][-1]["market"] == "KR"


def test_version_checked_migration_preserves_native_history_and_frozen_reference(service):
    from test_portfolio import activate as native_activate
    from test_portfolio import fill as native_fill
    native_activate(service)
    native_fill(service)
    with pytest.raises(Conflict, match="stopped"):
        command(service, "enable_global", now=NOW + 70000)
    command(service, "pause", now=NOW + 80000)
    with pytest.raises(Conflict, match="stopped_flat"):
        command(service, "enable_global", now=NOW + 81000)
    command(service, "resume", now=NOW + 82000)
    close = demo_snapshot("KR", NOW + 90000)
    close.update(closingSoon=True, id="native-closing-fixture")
    service.tick(NOW + 90000, close)
    assert not service.store.current()["session"]["positions"]
    command(service, "pause", now=NOW + 100000)
    old = deepcopy(service.store.current())
    receipt = command(service, "enable_global", now=NOW + 110000)
    new = service.store.current()
    for field in ("id", "cash", "baseline", "positions", "fills", "policy", "policyVersion"):
        assert old["session"][field] == new["session"][field]
    assert old["benchmark"] == new["benchmark"]
    assert not domain.standing_symbols(new["session"])
    assert new["session"]["config"]["capital"] == old["session"]["config"]["capital"]
    assert new["session"]["cashBalances"] == {"KRW": old["session"]["cash"], "USD": "0"}
    repeat = Command(command_id=f"enable_global-{NOW + 110000}", session_id=new["session"]["id"],
                     expected_version=old["session"]["version"], action="enable_global")
    assert service.command(repeat, NOW + 110000) == receipt


def test_global_schema_requires_qualified_scope_and_same_market_groups(service):
    value = activate(service)
    bad = deepcopy(value)
    bad["candidate_groups"][0]["candidates"][0].pop("market")
    with pytest.raises(ValueError):
        Proposal.model_validate(bad)
    bad = deepcopy(value)
    bad["candidate_groups"][0]["candidates"].extend(bad["candidate_groups"][1]["candidates"])
    with pytest.raises(ValueError):
        Proposal.model_validate(bad)
    state = service.store.current()["session"]
    parsed = Proposal.model_validate(value).model_copy(update={"allowed_symbols": ["NVDA"]})
    # Use a new active run so the scope check, not completed-run rejection, is exercised.
    service.claim("schema-check-run", NOW + 1, "Isolated schema validation",
                  state["id"], state["policyVersion"])
    parsed = parsed.model_copy(update={"run_id": "schema-check-run",
                                     "base_policy_version": state["policyVersion"]})
    assert service.validate_proposal(parsed, NOW + 1, state, service.store.db) == (
        "unsupported_symbols")


def test_global_collector_scopes_symbols_and_reuses_paced_reference_fx(monkeypatch):
    calls = []
    fx_calls = []
    monkeypatch.setattr("app.paper.market.time.time", lambda: NOW / 1000)
    async def collect(self, held, candidates, reference):
        calls.append((self.market, held, candidates, reference))
        period = {"startTime": "2026-09-30T00:00:00Z",
                  "endTime": "2026-09-30T23:59:00Z"}
        day = {"date": "2026-09-30", "regularMarket": period,
               "integrated": {"regularMarket": period}}
        self.calendar = {"data": {"today": day}}
    async def fx():
        fx_calls.append(True)
        return demo_snapshot("US", NOW)["fx"]
    monkeypatch.setattr(Collector, "collect", collect)
    monkeypatch.setattr(toss, "global_fx", fx)
    collector = GlobalCollector()
    async def run():
        for _ in range(2):
            await collector.collect(["KR:005930", "US:NVDA"], ["US:SH"], ["KR:000660"])
    asyncio.run(run())
    assert len(fx_calls) == 1
    assert calls[0] == ("KR", ["005930"], [], ["000660"])
    assert calls[1] == ("US", ["NVDA"], ["SH"], [])
    snapshot = collector.snapshot(NOW)
    assert snapshot["market"] == "GLOBAL" and snapshot["fx"]["validFrom"] == NOW


def test_public_fx_keeps_actual_source_and_rejects_expiry(monkeypatch):
    now = datetime.now(UTC)
    expiry = now + timedelta(minutes=5)
    async def request(endpoint, params, ttl):
        assert endpoint == "/api/v1/exchange-rate" and ttl == 300
        assert params == {"baseCurrency": "USD", "quoteCurrency": "KRW"}
        toss._cache[toss._cache_key(endpoint, params)] = (0, now.isoformat(), {})
        return {"rate": "1400", "validFrom": now.isoformat(), "validUntil": expiry.isoformat()}
    monkeypatch.setattr(toss, "_request", request)
    quote = asyncio.run(toss.global_fx())
    assert quote["validFrom"] == int(now.timestamp() * 1000)
    assert quote["receivedAt"] == int(now.timestamp() * 1000)
    expiry = now - timedelta(minutes=1)
    from fastapi import HTTPException
    with pytest.raises(HTTPException, match="Expired"):
        asyncio.run(toss.global_fx())


def test_global_rollback_cannot_select_native_code_and_replay_discloses_reference(service):
    from app.paper.strategies.contracts import Rollback
    from app.paper.strategies.evaluation import replay
    activate(service)
    state = fill(service)
    rollback = Rollback(command_id="bad-global-rollback", session_id=state["id"],
                        expected_policy_version=state["policyVersion"], target_ref="cash-v1@1",
                        reason="Fixture protocol-boundary rejection.")
    with pytest.raises(Conflict, match="global_protocol_required"):
        service.rollback_strategy(rollback, NOW + 70000)
    assert service.store.current()["session"]["policy"] == state["policy"]
    modules = {m["ref"]: service.strategies.get(m["ref"]) for m in service.strategies.catalog()}
    report = replay(state, [data(NOW + 30000), data(NOW + 60000)], modules, "test-global@1")
    assert not report["comparable_reference"]
    assert report["results"][0]["fills"] == 2
    assert all(result["errors"] == 0 for result in report["results"])
