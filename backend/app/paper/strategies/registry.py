"""Immutable source versions, executable checks, and attributable paper feedback."""

import json
import uuid
from copy import deepcopy
from decimal import Decimal

from app.paper.storage import encode
from app.paper.strategies.contracts import Draft
from app.paper.strategies.runtime import BUILTINS, StrategyError, digest, execute

CHECK_VERSION = 1


def reference(strategy_id, version=1):
    return f"{strategy_id}@{version}"


def fingerprint(draft):
    return digest(encode(draft.model_dump(mode="json")))


def scenarios():
    from app.paper.contracts import THEMES, standing_groups
    from app.paper.market import demo_snapshot

    now = 1790730000000
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
        cases.append((f"{market}_entry", deepcopy(context)))
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
    return cases


def check_draft(draft: Draft):
    results = []
    for name, context in scenarios():
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
                (reference(name), encode(draft.model_dump(mode="json")), digest(source)),
            )

    def get(self, ref):
        row = self.store.db.execute(
            "SELECT * FROM strategy_versions WHERE ref=?", (ref,)
        ).fetchone()
        if not row:
            raise StrategyError("strategy_not_registered")
        return {
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
        return execute(item["source"], context)

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
            payload = encode(draft.model_dump(mode="json"))
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
                entry["closed_trades"] += 1
                entry["realized_net"] += profit
                entry["winning_trades"] += profit > 0
                entry["sessions"].add(state["id"])
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
