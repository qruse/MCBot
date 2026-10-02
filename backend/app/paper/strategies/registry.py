"""Immutable source versions, executable checks, and attributable paper feedback."""

import json
import uuid
from copy import deepcopy
from decimal import Decimal

from app.paper.storage import encode
from app.paper.strategies.contracts import Draft
from app.paper.strategies.runtime import BUILTINS, StrategyError, digest, execute, prepare_context

CHECK_VERSION = 5


def reference(strategy_id, version=1):
    return f"{strategy_id}@{version}"


def draft_payload(draft):
    payload = draft.model_dump(mode="json")
    # Preserve exact v1 payload identity for pre-upgrade idempotent registrations.
    if payload["protocol_version"] == 1:
        payload.pop("protocol_version")
    return payload


def fingerprint(draft):
    return digest(encode(draft_payload(draft)))


def scenarios(protocol_version=1):
    from app.paper.contracts import THEMES, standing_groups
    from app.paper.market import demo_snapshot

    now = 1790730000000
    if protocol_version == 5:
        return global_scenarios(now)
    cases = []
    for market in ("KR", "US"):
        data = demo_snapshot(market, now)
        groups = {
            **THEMES[market],
            **{
                g["group_id"]: [c["symbol"] for c in g["candidates"]]
                for g in standing_groups(market)
            },
        }
        context = {
            "protocol_version": 1,
            "now": now,
            "data": data,
            "groups": groups,
            "positions": [],
            "cash": "100000000",
            "capital": "100000000",
            "active_symbols": [],
            "can_enter": True,
            "candidate_ready": list(data["quotes"]),
            "minute_ready": list(data["quotes"]),
        }
        if protocol_version >= 3:
            members = sorted({s for group in groups.values() for s in group})
            # Deterministic exact-sum targets for all monitored fixture instruments and cash.
            weights = {s: "0.1" for s in members}
            weights["CASH"] = str(Decimal(1) - Decimal("0.1") * len(members))
            context["portfolio"] = {"target_weights": weights}
            context["portfolio_runtime"] = {"last_slot": None, "risk_blocks": {}}
            if protocol_version == 4:
                context["portfolio"].update(mode="adaptive", retirements=[])
        cases.append((f"{market}_entry", deepcopy(context)))
        if protocol_version >= 2:
            members = next(iter(groups.values()))
            for size in (1, 2):
                short = deepcopy(context)
                short["groups"] = {f"{market.lower()}-semis": members[:size]}
                if protocol_version >= 3:
                    short["portfolio"]["target_weights"] = {
                        **{s: "0.1" for s in members[:size]},
                        "CASH": str(Decimal(1) - Decimal("0.1") * size),
                    }
                cases.append((f"{market}_{size}_member_entry", short))
        if protocol_version == 4:
            zero_cash = deepcopy(context)
            selected = next(iter(groups.values()))[0]
            zero_cash["groups"] = {"single-stock": [selected]}
            zero_cash["portfolio"]["target_weights"] = {selected: "1", "CASH": "0"}
            cases.append((f"{market}_zero_cash_entry", zero_cash))
            rotation = deepcopy(context)
            retired = next(iter(rotation["portfolio"]["target_weights"]))
            rotation["groups"] = {
                name: [s for s in group if s != retired]
                for name, group in groups.items()
                if any(s != retired for s in group)
            }
            rotation["portfolio"]["target_weights"][retired] = "0"
            rotation["portfolio"]["target_weights"]["CASH"] = "0.4"
            rotation["portfolio"]["retirements"] = [{"symbol": retired}]
            cases.append((f"{market}_retirement_entry", rotation))
        symbol = next(iter(data["quotes"]))
        context.update(
            can_enter=False,
            active_symbols=next(iter(groups.values())),
            positions=[
                {
                    "symbol": symbol,
                    "name": symbol,
                    "shares": 1,
                    "entryPrice": "100",
                    "entryCost": "100",
                    "entryFee": "0",
                    "entryFx": "1",
                    "entrySourceTime": now - 30000,
                    "policyVersion": 1,
                    "proposalId": "test",
                    "entryId": "test-entry",
                    "strategyRef": "theme-top3-v1@1",
                }
            ],
        )
        cases.append((f"{market}_held", deepcopy(context)))
        context.update(candidate_ready=[], minute_ready=[])
        data["minute"] = {}
        data["daily"] = {}
        data["quotes"] = {}
        cases.append((f"{market}_missing_data", deepcopy(context)))
        data["marketOpen"] = False
        cases.append((f"{market}_closed", deepcopy(context)))
    return [(name, prepare_context(context, protocol_version)) for name, context in cases]


def global_scenarios(now):
    from app.paper.global_account import combine
    from app.paper.market import demo_snapshot
    markets = {m: demo_snapshot(m, now) for m in ("KR", "US")}
    data = combine(markets, now, markets["US"]["fx"])
    context = {
        "protocol_version": 5, "now": now, "data": data,
        "groups": {"kr": ["KR:005930"], "us": ["US:NVDA"]}, "positions": [],
        "cash": "10000000", "capital": "10000000", "cash_balances": {"KRW": "10000000",
                                                                                  "USD": "0"},
        "active_symbols": [], "can_enter": True,
        "candidate_ready": list(data["quotes"]), "minute_ready": list(data["quotes"]),
        "active_candidates": ["KR:005930", "US:NVDA"],
        "portfolio": {"mode": "adaptive", "retirements": [], "target_weights": {
            "KR:005930": "0.3", "US:NVDA": "0.3", "CASH": "0.4"}},
        "portfolio_runtime": {"last_slot": None, "risk_blocks": {}},
    }
    cases = [("GLOBAL_both_entry", deepcopy(context))]
    for market in ("KR", "US"):
        value = deepcopy(context)
        closed = "US" if market == "KR" else "KR"
        value["data"]["markets"][closed]["marketOpen"] = False
        value["active_candidates"] = [v for v in context["active_candidates"]
                                      if v.startswith(market + ":")]
        cases.append((f"GLOBAL_{market}_open_entry", value))
    zero = deepcopy(context)
    zero["portfolio"]["target_weights"].update({"KR:005930": "0.5", "US:NVDA": "0.5",
                                                "CASH": "0"})
    cases.append(("GLOBAL_zero_cash_entry", zero))
    retirement = deepcopy(context)
    retirement["portfolio"]["target_weights"]["KR:000660"] = "0"
    retirement["portfolio"]["retirements"] = [{"market": "KR", "symbol": "000660"}]
    cases.append(("GLOBAL_retirement_entry", retirement))
    missing = deepcopy(context)
    missing["candidate_ready"] = []
    missing["data"]["fx"] = None
    cases.append(("GLOBAL_missing_entry", missing))
    context["can_enter"] = False
    cases.append(("GLOBAL_held", deepcopy(context)))
    context["data"]["marketOpen"] = False
    for item in context["data"]["markets"].values():
        item["marketOpen"] = False
    cases.append(("GLOBAL_closed", context))
    return [(name, prepare_context(c, 5)) for name, c in cases]


def check_draft(draft: Draft):
    results = []
    for name, context in scenarios(draft.protocol_version):
        try:
            output = execute(draft.source, context)
            if name.endswith("_entry") and execute(draft.source, context) != output:
                raise StrategyError("nondeterministic_strategy")
            results.append({"case": name, "passed": True})
        except StrategyError as error:
            results.append({"case": name, "passed": False, "reason": str(error)})
            break
    return {
        "id": uuid.uuid4().hex,
        "kind": "contract_checks",
        "check_version": CHECK_VERSION,
        "draft_fingerprint": fingerprint(draft),
        "source_digest": digest(draft.source),
        "strategy_ref": reference(draft.strategy_id, draft.version),
        "passed": bool(results) and all(r["passed"] for r in results),
        "cases": results,
        "profitability_validated": False,
    }


class Registry:
    def __init__(self, store):
        self.store = store
        store.db.executescript("""
            CREATE TABLE IF NOT EXISTS strategy_versions(
                ref TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL,
                registered INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS strategy_evaluations(
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, created INTEGER NOT NULL);
            INSERT OR IGNORE INTO migrations VALUES(2);
        """)
        for name, source in BUILTINS.items():
            draft = Draft(
                strategy_id=name,
                version=1,
                parent_ref="",
                name=name,
                hypothesis="Frozen reference behavior.",
                failure_criterion="Regression or risk invariant failure.",
                source=source,
            )
            store.db.execute(
                "INSERT OR IGNORE INTO strategy_versions VALUES(?,?,?,0)",
                (reference(name), encode(draft_payload(draft)), digest(source)),
            )

    def get(self, ref):
        row = self.store.db.execute(
            "SELECT * FROM strategy_versions WHERE ref=?", (ref,)
        ).fetchone()
        if not row:
            raise StrategyError("strategy_not_registered")
        return {
            "protocol_version": 1,
            **json.loads(row["payload"]),
            "ref": ref,
            "digest": row["digest"],
            "registered_at": row["registered"],
        }

    def run(self, ref, context, expected_digest=None):
        item = self.get(ref)
        if digest(item["source"]) != item["digest"] or (
            expected_digest and item["digest"] != expected_digest
        ):
            raise StrategyError("strategy_digest_mismatch")
        return execute(item["source"], prepare_context(context, item["protocol_version"]))

    def record(self, report, now):
        report = {**report, "created_at": now}
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO strategy_evaluations VALUES(?,?,?)",
                (report["id"], encode(report), now),
            )
        return report

    def register(self, draft, evaluation_id, now):
        ref = reference(draft.strategy_id, draft.version)
        with self.store.transaction() as db:
            existing = db.execute(
                "SELECT payload FROM strategy_versions WHERE ref=?", (ref,)
            ).fetchone()
            payload = encode(draft_payload(draft))
            if existing:
                if existing[0] != payload:
                    raise StrategyError("strategy_version_immutable")
                return self.get(ref)
            if draft.strategy_id in BUILTINS:
                raise StrategyError("builtin_strategy_reserved")
            parent = self.get(draft.parent_ref)
            if draft.version > 1 and draft.parent_ref != reference(
                draft.strategy_id, draft.version - 1
            ):
                raise StrategyError("strategy_parent_mismatch")
            if parent["strategy_id"] == draft.strategy_id and parent["version"] >= draft.version:
                raise StrategyError("strategy_parent_mismatch")
            row = db.execute(
                "SELECT payload FROM strategy_evaluations WHERE id=?", (evaluation_id,)
            ).fetchone()
            report = json.loads(row[0]) if row else {}
            if (
                not report.get("passed")
                or report.get("kind") != "contract_checks"
                or report.get("check_version") != CHECK_VERSION
                or report.get("draft_fingerprint") != fingerprint(draft)
                or not 0 <= now - report.get("created_at", 0) <= 86400000
            ):
                raise StrategyError("strategy_checks_required")
            db.execute(
                "INSERT INTO strategy_versions VALUES(?,?,?,?)",
                (ref, payload, digest(draft.source), now),
            )
        return self.get(ref)

    def catalog(self):
        items = []
        for row in self.store.db.execute(
            "SELECT ref FROM strategy_versions ORDER BY registered DESC,ref"
        ):
            item = self.get(row[0])
            item.pop("source")
            item["status"] = "builtin" if item["strategy_id"] in BUILTINS else "paper_ready"
            items.append(item)
        return items

    def feedback(self):
        totals = {}
        for row in self.store.db.execute("SELECT payload FROM sessions"):
            state = json.loads(row[0])["session"]
            open_ids = {p.get("entryId") for p in state["positions"]}
            trade_results = {}
            for fill in state["fills"]:
                if fill["side"] != "sell":
                    continue
                ref = fill.get("strategyRef", "theme-top3-v1@1")
                key = (ref, state["source"])
                entry = totals.setdefault(
                    key,
                    {
                        "strategy_ref": ref,
                        "source": state["source"],
                        "closed_trades": 0,
                        "realized_net": Decimal(0),
                        "winning_trades": 0,
                        "sessions": set(),
                    },
                )
                profit = Decimal(fill["netProfit"])
                entry["realized_net"] += profit
                entry["sessions"].add(state["id"])
                trade_key = (key, fill.get("entryId", fill["id"]))
                trade_results[trade_key] = trade_results.get(trade_key, Decimal(0)) + profit
            for (key, entry_id), profit in trade_results.items():
                if entry_id not in open_ids:
                    totals[key]["closed_trades"] += 1
                    totals[key]["winning_trades"] += profit > 0
        return [
            {
                **entry,
                "realized_net": str(entry["realized_net"]),
                "sessions": len(entry["sessions"]),
            }
            for entry in totals.values()
        ]

    def evaluations(self):
        return [
            json.loads(row[0])
            for row in self.store.db.execute(
                "SELECT payload FROM strategy_evaluations ORDER BY created DESC LIMIT 20"
            )
        ]
