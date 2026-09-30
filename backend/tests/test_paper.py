"""Focused end-to-end domain/storage/exchange cases, all market data is synthetic."""

import asyncio
import json
from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.paper import domain
from app.paper.contracts import THEMES, Command, Settings, symbols
from app.paper.market import Collector, demo_snapshot
from app.paper.service import Conflict, PaperService

NOW = 1790730000000


@pytest.fixture
def service(tmp_path):
    item = PaperService(tmp_path / "ledger.db", tmp_path / "exchange")
    yield item
    item.store.db.close()


def command(service, action, now=NOW, **kwargs):
    current = service.store.current()["session"]
    cmd = Command(
        command_id=f"{action}-{now}",
        session_id=current["id"],
        expected_version=current["version"],
        action=action,
        **kwargs,
    )
    return service.command(cmd, now)


def start(service, mode="adaptive", market="KR"):
    command(service, "new", settings=Settings(source="demo", mode=mode, market=market))
    command(service, "start")
    service.tick(NOW, demo_snapshot(market, NOW))


def proposal(service, now=NOW, **changes):
    run_id = f"run-{now}"
    service.claim(run_id, now)
    manifest = json.loads((service.exchange / "latest.json").read_text())
    s = service.store.current()["session"]
    market = s["config"]["market"]
    value = {
        "schema_version": 4,
        "proposal_id": f"proposal-{now}",
        "run_id": run_id,
        "session_id": s["id"],
        "snapshot_id": manifest["snapshot_id"],
        "market": s["config"]["market"],
        "base_policy_version": s["policyVersion"],
        "as_of": now,
        "valid_from": now,
        "expires_at": now + 3600000,
        "playbook_id": "theme-top3-v1",
        "allowed_symbols": THEMES[market][f"{market.lower()}-semis"][:],
        "candidate_groups": [
            {
                "group_id": name,
                "name": name,
                "candidates": [
                    {
                        "symbol": symbol,
                        "name": symbol,
                        "rationale": "Synthetic selection test.",
                        "evidence_ids": ["fixture-evidence"],
                    }
                    for symbol in group
                ],
            }
            for name, group in THEMES[s["config"]["market"]].items()
            if name.endswith("-semis")
        ],
        "hypothesis": "Trend remains eligible.",
        "counterevidence": "Modeled costs and synthetic inputs cannot validate profitability.",
        "rationale": "Fixture proposal for lifecycle verification.",
        "evidence": [
            {
                "evidence_id": "fixture-evidence",
                "source_url": "https://example.com/test",
                "publisher": "Synthetic test",
                "published_at": now - 10000,
                "retrieved_at": now,
                "claim": "Synthetic test only.",
                "excerpt": "",
                "uncertainty": "No real market evidence.",
            }
        ],
        **changes,
    }
    return value


def activate(service):
    p = proposal(service)
    assert service.submit(p, p["proposal_id"], NOW)["status"] == "accepted"
    service.tick(NOW + 30000, demo_snapshot("KR", NOW + 30000))
    service.tick(NOW + 60000, demo_snapshot("KR", NOW + 60000))


def test_ledger_delayed_fills_risk_and_reconciliation(service):
    start(service)
    activate(service)
    s = service.store.current()["session"]
    assert len(s["positions"]) == 3
    assert all(f["timestamp"] > NOW + 30000 for f in s["fills"])
    assert all(p["policyVersion"] == 1 for p in s["positions"])
    assert Decimal(s["cash"]) >= 0
    before = deepcopy(s)
    data = demo_snapshot("KR", NOW + 90000)
    data["minute"].pop("114800")
    data["quotes"]["005930"]["price"] = "69000"
    service.tick(NOW + 90000, data)
    s = service.store.current()["session"]
    assert len(s["positions"]) == 2
    assert s["fills"][-1]["reason"] == "position_stop"
    service.tick(NOW + 90000, data)
    assert len(service.store.current()["session"]["fills"]) == len(s["fills"])
    value = domain.equity(s, data, NOW + 90000)
    assert value - Decimal(s["baseline"]) == Decimal(s["samples"][-1]["profit"])
    assert sum(Decimal(p["entryCost"]) for p in before["positions"]) + Decimal(
        before["cash"]
    ) == Decimal(before["baseline"])


def test_demo_to_toss_archives_without_transferring_synthetic_holdings(service):
    start(service)
    activate(service)
    settings = Settings(source="toss", mode="adaptive", capital=10000000)
    with pytest.raises(Conflict, match="stop_before_new_session"):
        command(service, "use_toss", settings=settings)
    command(service, "pause", NOW + 61000)
    before = deepcopy(service.store.current()["session"])
    with pytest.raises(Conflict, match="positions_require_exit"):
        command(service, "new", NOW + 62000, settings=settings)
    with pytest.raises(Conflict, match="demo_to_toss_only"):
        command(service, "use_toss", settings=Settings(source="demo"))
    cmd = Command(
        command_id="source-transition", session_id=before["id"],
        expected_version=before["version"], action="use_toss", settings=settings,
    )
    receipt = service.command(cmd, NOW + 63000)
    assert service.command(cmd, NOW + 64000) == receipt
    archived = service.view(before["id"])["session"]
    for key in ("positions", "fills", "cash", "baseline", "policy"):
        assert archived[key] == before[key]
    assert archived["events"][-1]["code"] == "demo_archived_for_toss"
    current = service.store.current()["session"]
    assert current["id"] != before["id"]
    assert current["source"] == "toss" and current["lifecycle"] == "idle"
    assert not current["positions"] and not current["fills"] and current["policy"] is None
    assert Decimal(current["config"]["capital"]) == 10000000
    assert service.store.db.execute(
        "SELECT active FROM sessions WHERE id=?", (before["id"],)
    ).fetchone()[0] == 0
    with pytest.raises(Conflict, match="demo_to_toss_only"):
        command(service, "use_toss", NOW + 65000, settings=settings)


def test_expired_policy_still_runs_stops_and_invalid_quote_never_fills(service):
    start(service)
    activate(service)
    now = NOW + 3601000
    data = demo_snapshot("KR", now)
    data["quotes"]["005930"].update(price="68000", sourceTime=now - 180000)
    data["quotes"]["000660"]["price"] = "170000"
    data["minute"] = {}
    service.tick(now, data)
    s = service.store.current()["session"]
    assert s["entryBlock"] == "policy_expired"
    assert "005930" in [p["symbol"] for p in s["positions"]]
    assert "000660" not in [p["symbol"] for p in s["positions"]]
    assert s["gaps"][-1]["reason"] == "data_stale"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"stop_percent": 3}, "invalid_schema"),
        ({"expires_at": NOW + 4500001}, "validity_exceeds_75_minutes"),
        ({"base_policy_version": 99}, "policy_version_conflict"),
        ({"allowed_symbols": ["NOT_ADMITTED"]}, "unsupported_symbols"),
        ({"as_of": NOW + 1000}, "invalid_evidence_cutoff"),
        ({"evidence": []}, "evidence_required"),
    ],
)
def test_proposal_rejections(service, change, reason):
    start(service)
    p = proposal(service, **change)
    receipt = service.submit(p, p["proposal_id"], NOW)
    assert receipt["reason"] == reason
    assert service.store.current()["session"]["policy"] is None
    assert service.submit(p, p["proposal_id"], NOW + 1) == receipt


def test_atomic_commands_restart_and_hour_slot(tmp_path):
    path, exchange = tmp_path / "test.db", tmp_path / "exchange"
    first = PaperService(path, exchange)
    start(first)
    cmd = Command(
        command_id="stop-id",
        session_id=first.store.current()["session"]["id"],
        expected_version=1,
        action="pause",
    )
    receipt = first.command(cmd, NOW + 1000)
    assert first.command(cmd, NOW + 2000) == receipt
    with pytest.raises(Conflict, match="version_conflict"):
        first.command(
            Command(
                command_id="old", session_id=cmd.session_id, expected_version=0, action="resume"
            ),
            NOW,
        )
    command(first, "resume", NOW + 3000)
    first.claim("run1", NOW)
    with pytest.raises(Conflict, match="hourly_slot"):
        first.claim("run2", NOW + 1000)
    state = first.store.current()["session"]
    first.store.db.close()
    restored = PaperService(path, exchange)
    recovered = restored.store.current()["session"]
    assert recovered["lifecycle"] == "paused"
    assert (recovered["cash"], recovered["baseline"], recovered["fills"]) == (
        state["cash"],
        state["baseline"],
        state["fills"],
    )
    assert recovered["gaps"][-1]["reason"] == "restart_paused"
    restored.store.db.close()


def test_owner_review_preserves_ledger_and_hourly_slot(service):
    start(service)
    p = proposal(service)
    service.submit(p, p["proposal_id"], NOW)
    before = service.store.current()["session"]
    args = ("Owner explicitly requested another demo entry", before["id"], 1)
    with pytest.raises(Conflict, match="policy_version_conflict"):
        service.claim("manual", NOW + 1000, args[0], before["id"], 0)
    receipt = service.claim("manual", NOW + 1000, *args)
    assert service.claim("manual", NOW + 2000, *args) == receipt
    with pytest.raises(Conflict, match="run_id_reused"):
        service.claim("manual", NOW + 2000, "Changed request", before["id"], 1)
    with pytest.raises(Conflict, match="research_run_in_progress"):
        service.claim("manual2", NOW + 2000, *args)
    with pytest.raises(Conflict, match="hourly_slot_already_claimed"):
        service.claim("scheduled", NOW + 2000)
    current = service.store.current()["session"]
    assert (current["cash"], current["baseline"], current["fills"], current["policy"]) == (
        before["cash"],
        before["baseline"],
        before["fills"],
        before["policy"],
    )
    assert current["events"][-1]["reason"] == args[0]
    manifest = json.loads((service.exchange / "latest.json").read_text())
    manual = {
        **p,
        "proposal_id": "manual-plan",
        "run_id": "manual",
        "snapshot_id": manifest["snapshot_id"],
        "base_policy_version": 1,
        "as_of": NOW + 3000,
        "valid_from": NOW + 3000,
    }
    assert service.submit(manual, "manual-plan", NOW + 3000)["status"] == "accepted"
    assert service.store.current()["session"]["policyVersion"] == 2


def test_observer_receipt_shadow_and_experiment_preregistration(service):
    start(service, "observer")
    p = proposal(
        service,
        experiment={
            "experiment_id": "exp1",
            "hypothesis": "Cash avoids losses.",
            "failure_criterion": "Five forward sessions underperform reference after costs.",
            "minimum_sessions": 5,
            "review_after": NOW + 86400000,
        },
    )
    path = service.exchange / "inbox" / f"{p['proposal_id']}.json"
    path.write_text(json.dumps(p))
    (service.exchange / "inbox" / "partial.tmp").write_text('{"proposal_id":')
    service.tick(NOW + 30000, demo_snapshot("KR", NOW + 30000))
    view = service.view()
    assert not view["session"]["positions"]
    assert len(service.store.current()["benchmark"]["positions"]) == 3
    assert (
        json.loads((service.exchange / "receipts" / path.name).read_text())["status"] == "observed"
    )
    assert view["research"]["experiments"][0]["independent_sessions"] == 0
    assert not view["research"]["experiments"][0]["promotion_eligible"]
    assert view["research"]["paired"]


def test_closed_market_and_lease_expiry_do_not_fill(service):
    start(service)
    activate(service)
    s = service.store.current()["session"]
    now = s["leaseUntil"] + 1
    data = demo_snapshot("KR", now)
    data["marketOpen"] = False
    service.tick(now, data)
    current = service.store.current()["session"]
    assert current["lifecycle"] == "paused"
    assert current["fills"] == s["fills"]


def test_local_api_no_provider_on_read_or_idle(monkeypatch):
    def no_provider(*args, **kwargs):
        raise AssertionError("Provider must not be called")

    monkeypatch.setattr("app.toss._request", no_provider)
    with TestClient(app) as client:
        assert client.get("/paper/snapshot").json()["session"]["lifecycle"] == "idle"
        assert client.get("/health").json()["database"]["database"] == "sqlite"
        cmd = {
            "command_id": "one",
            "expected_version": 0,
            "action": "start",
            "session_id": client.get("/paper/snapshot").json()["session"]["id"],
        }
        assert client.post("/paper/commands", json=cmd).status_code == 403
        headers = {"X-MCBot-Command": "local-paper", "Origin": "https://untrusted.test"}
        assert client.post("/paper/commands", json=cmd, headers=headers).status_code == 403
        headers.pop("Origin")
        assert client.post("/paper/commands", json=cmd, headers=headers).status_code == 200


def test_sidecar_independent_of_candidates_and_domestic_ignores_fx(service):
    start(service)
    activate(service)
    data = demo_snapshot("KR", NOW + 90000)
    data["fx"] = None
    data["minute"].pop("114800")
    for symbol in ["005930", "000660", "042700"]:
        data["quotes"][symbol]["price"] = str(
            Decimal(data["quotes"][symbol]["price"]) * Decimal(".9")
        )
    service.tick(NOW + 90000, data)
    s = service.store.current()["session"]
    assert s["lifecycle"] == "halted"
    assert s["positions"] == []
    assert len([f for f in s["fills"] if f["reason"] == "sidecar_halt"]) == 3
    assert Decimal(s["samples"][-1]["equity"]) == Decimal(s["cash"])
    with pytest.raises(Conflict, match="invalid_lifecycle"):
        command(service, "resume", NOW + 120000)


def test_malformed_submission_cannot_poison_future_evidence(service):
    start(service)
    assert service.submit({"evidence": [1]}, "bad", NOW)["reason"] == "invalid_schema"
    p = proposal(service)
    assert service.submit(p, p["proposal_id"], NOW)["status"] == "accepted"
    changed = {**p, "rationale": "Different content"}
    assert service.submit(changed, p["proposal_id"], NOW)["reason"] == "proposal_id_reused"


def selected_groups():
    return [
        {
            "group_id": "agent-growth",
            "name": "Research selection",
            "candidates": [
                {
                    "symbol": symbol,
                    "name": f"Test {symbol}",
                    "rationale": "Fixture selection rationale.",
                    "evidence_ids": ["fixture-evidence"],
                }
                for symbol in ["035420", "035720", "005380"]
            ],
        }
    ]


def selected_input(now):
    data = demo_snapshot("KR", now)
    for original, symbol in zip(symbols("KR")[:3], ["035420", "035720", "005380"], strict=True):
        for area in ("quotes", "minute", "daily", "securities"):
            data[area][symbol] = deepcopy(data[area][original])
        data["securities"][symbol].update(symbol=symbol, name=f"Test {symbol}")
    return data


def test_agent_can_choose_new_symbols_and_partial_data_cannot_enter(service):
    start(service)
    p = proposal(
        service, candidate_groups=selected_groups(), allowed_symbols=["035420", "035720", "005380"]
    )
    receipt = service.submit(p, p["proposal_id"], NOW)
    assert receipt["status"] == "accepted"
    assert receipt["candidate_gate"] == "pending_provider_validation"
    data = selected_input(NOW + 30000)
    data["securities"].pop("035720")
    service.tick(NOW + 30000, data)
    s = service.store.current()["session"]
    assert s["total"] == 6 and s["ready"] == 5
    assert not s["fills"]
    data = selected_input(NOW + 60000)
    data["securities"]["035720"]["koreanMarketDetail"]["krxTradingSuspended"] = True
    service.tick(NOW + 60000, data)
    assert not service.store.current()["session"]["fills"]
    stale_halt = selected_input(NOW + 60000)
    stale_halt["securities"]["035720"] = deepcopy(data["securities"]["035720"])
    stale_halt["securities"]["035720"]["receivedAt"] = NOW - 400000
    assert domain.price("035720", stale_halt, NOW + 60000) is None
    service.tick(NOW + 90000, selected_input(NOW + 90000))
    service.tick(NOW + 120000, selected_input(NOW + 120000))
    s = service.store.current()["session"]
    assert {p["symbol"] for p in s["positions"]} == {"035420", "035720", "005380"}
    assert set(domain.candidate_symbols(service.store.current()["benchmark"])) == set(symbols("KR"))
    assert s["activeSymbols"] == ["035420", "035720", "005380"]
    service.export(NOW + 120000)
    manifest = json.loads((service.exchange / "latest.json").read_text())
    export = json.loads(
        (service.exchange / "exports" / manifest["snapshot_id"] / "context.json").read_text()
    )
    assert set(export["features"]) == {"035420", "035720", "005380", "114800", "123310", "145670"}


def test_replaced_candidates_keep_old_holding_protection(service):
    start(service)
    activate(service)
    now = NOW + 3600000
    service.tick(now, selected_input(now))
    p = proposal(
        service,
        now=now,
        candidate_groups=selected_groups(),
        allowed_symbols=["035420", "035720", "005380"],
        evidence=[
            {
                "evidence_id": "replacement",
                "source_url": "https://example.com/new",
                "publisher": "Test",
                "published_at": now,
                "retrieved_at": now,
                "claim": "Test",
                "excerpt": "",
                "uncertainty": "Synthetic",
            }
        ],
    )
    for group in p["candidate_groups"]:
        for c in group["candidates"]:
            c["evidence_ids"] = ["replacement"]
    assert service.submit(p, p["proposal_id"], now)["status"] == "accepted"
    data = selected_input(now + 30000)
    data["minute"].pop("035420")
    data["quotes"]["005930"]["price"] = "68000"
    service.tick(now + 30000, data)
    s = service.store.current()["session"]
    assert s["fills"][-1]["symbol"] == "005930"
    assert s["fills"][-1]["reason"] == "position_stop"
    assert s["fills"][-1]["policyVersion"] == 1
    assert "000660" in domain.protected_symbols(s)
    assert s["policyVersion"] == 2


def test_candidate_evidence_and_identity_validation(service):
    start(service)
    groups = selected_groups()
    groups[0]["candidates"][1]["evidence_ids"] = ["not_in_proposal"]
    p = proposal(service, candidate_groups=groups, allowed_symbols=["035420", "035720", "005380"])
    assert service.submit(p, p["proposal_id"], NOW)["reason"] == "candidate_evidence_missing"
    assert not service.store.current()["session"]["candidateGroups"]


def test_collector_preserves_holdings_and_collects_only_dynamic_plus_reference(monkeypatch):
    async def run():
        collector = Collector("KR")
        data = selected_input(NOW)
        collector.securities = deepcopy(data["securities"])
        collector.updated["calendar"] = NOW
        collector.updated.update({f"stock:{s}": NOW for s in data["securities"]})
        calls = []

        async def prices(selected):
            calls.append(selected.split(","))
            return {"data": [{"symbol": s} for s in selected.split(",")]}

        monkeypatch.setattr("app.paper.market.time.time", lambda: NOW / 1000)
        monkeypatch.setattr("app.paper.market.calendar_state", lambda *args: {"marketOpen": True})
        monkeypatch.setattr("app.toss.prices", prices)
        monkeypatch.setattr("app.toss.status", lambda: {"state": "ready"})
        await collector.collect(["005930"], ["035420", "035720", "005380"], ["114800"])
        assert calls == [["005930", "035420", "035720", "005380", "114800"]]
        assert "005930" in collector.securities
        assert "000660" not in collector.securities

    asyncio.run(run())


def falling_market(market, now):
    """Explicit fixture: ordinary candidates fall while standing inverse ETFs rise."""
    data = demo_snapshot(market, now)
    from app.paper.contracts import standing_groups

    pinned = {item["symbol"] for item in standing_groups(market)[0]["candidates"]}
    for symbol, quote in data["quotes"].items():
        slope = Decimal(".003") if symbol in pinned else Decimal("-.001")
        quote["changePercent"] = "1.5" if symbol in pinned else "-1"
        for interval in ("minute", "daily"):
            bars = data[interval][symbol]["candles"]
            base = Decimal(quote["price"])
            for i, bar in enumerate(bars):
                bar["close"] = str(base * (1 + (i - len(bars) + 1) * slope))
    return data


@pytest.mark.parametrize("market", ["KR", "US"])
def test_standing_inverse_can_enter_without_agent_symbols_and_retains_risk(service, market):
    start(service, market=market)
    s = service.store.current()["session"]
    pinned = set(domain.standing_symbols(s))
    assert len(pinned) == 3 and not s["candidateGroups"]
    service.tick(NOW + 30000, falling_market(market, NOW + 30000))
    assert not service.store.current()["session"]["fills"]  # Inclusion alone cannot enter.
    p = proposal(service, now=NOW + 30000, candidate_groups=[], allowed_symbols=[])
    assert service.submit(p, p["proposal_id"], NOW + 30000)["status"] == "accepted"
    service.tick(NOW + 60000, falling_market(market, NOW + 60000))
    assert not service.store.current()["session"]["positions"]  # Wait for a later price.
    data = falling_market(market, NOW + 90000)
    service.tick(NOW + 90000, data)
    s = service.store.current()["session"]
    assert {p["symbol"] for p in s["positions"]} == pinned
    assert s["activeTheme"] == f"{market.lower()}-standing-inverse-v1"
    assert Decimal(s["cash"]) >= 0
    service.tick(NOW + 90000, data)
    assert len(service.store.current()["session"]["fills"]) == 3
    stopped = s["positions"][0]["symbol"]
    data = falling_market(market, NOW + 120000)
    data["quotes"][stopped]["price"] = str(
        Decimal(data["quotes"][stopped]["price"]) * Decimal(".97")
    )
    service.tick(NOW + 120000, data)
    s = service.store.current()["session"]
    assert s["fills"][-1]["reason"] == "position_stop"
    assert s["fills"][-1]["symbol"] == stopped
    assert not service.store.current()["benchmark"].get("standingGroups")


@pytest.mark.parametrize("gate", ["cash", "expired", "blocked", "stale", "observer", "v2"])
def test_standing_candidates_never_bypass_entry_gates(service, gate):
    start(service, mode="observer" if gate == "observer" else "adaptive")
    p = proposal(service, candidate_groups=[], allowed_symbols=[])
    if gate == "cash":
        p["playbook_id"] = "cash-v1"
    if gate == "expired":
        p["expires_at"] = NOW + 10000
    if gate == "blocked":
        p["entry_blocks"] = ["114800"]
    if gate == "v2":
        p["schema_version"] = 2
    receipt = service.submit(p, p["proposal_id"], NOW)
    assert receipt["status"] == (
        "rejected" if gate == "v2" else "observed" if gate == "observer" else "accepted"
    )
    for now in (NOW + 30000, NOW + 60000):
        data = falling_market("KR", now)
        if gate == "stale":
            data["minute"].pop("114800")
        service.tick(now, data)
    s = service.store.current()["session"]
    assert not s["fills"]
    assert set(domain.collection_symbols(s, NOW + 5000000)) == {"114800", "123310", "145670"}


def test_pinned_identity_is_reserved_and_persists_after_restart(service):
    start(service)
    p = proposal(service)
    p["candidate_groups"][0]["candidates"][0]["symbol"] = "114800"
    p["allowed_symbols"][0] = "114800"
    assert service.submit(p, p["proposal_id"], NOW)["reason"] == "standing_candidate_duplicate"
    s = service.store.current()["session"]
    reopened = PaperService(
        service.store.db.execute("PRAGMA database_list").fetchone()[2], service.exchange
    )
    try:
        restored = reopened.store.current()["session"]
        assert restored["standingGroups"] == s["standingGroups"]
        assert restored["lifecycle"] == "paused"
        assert set(domain.collection_symbols(restored, NOW + 5000000)) == {
            "114800",
            "123310",
            "145670",
        }
    finally:
        reopened.store.db.close()
