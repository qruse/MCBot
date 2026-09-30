"""Diagnostic replay of recorded inputs; never writes operational sessions or orders."""

import uuid
from copy import deepcopy
from decimal import Decimal

from app.paper import domain
from app.paper.contracts import Settings
from app.paper.strategies.runtime import StrategyError, digest, execute


def replay(original, inputs, modules, target_ref):
    def runner(ref, context, expected_digest=None):
        item = modules.get(ref)
        if not item or (expected_digest and digest(item["source"]) != expected_digest):
            raise StrategyError("strategy_digest_mismatch")
        return execute(item["source"], context)

    results = []
    for ref in (target_ref, "theme-top3-v1@1"):
        module = modules[ref]
        settings = Settings(
            market=original["config"]["market"],
            capital=original["config"]["capital"],
            source=original["source"],
            mode="adaptive",
        )
        state = domain.create(settings, "replay")
        state.update(
            lifecycle="preparing",
            candidateGroups=deepcopy(original.get("candidateGroups", [])),
            standingGroups=deepcopy(original.get("standingGroups", [])),
        )
        state["policy"] = {
            "schema_version": 4,
            "playbook_id": module["strategy_id"],
            "strategy_version": module["version"],
            "strategy_digest": module["digest"],
            "proposal_id": "diagnostic-replay",
            "max_exposure_percent": "100",
            "entry_blocks": [],
            "allowed_symbols": [
                c["symbol"] for g in state["candidateGroups"] for c in g["candidates"]
            ],
            "valid_from": 0,
            "expires_at": 2**53,
        }
        peak = Decimal(settings.capital)
        drawdown = Decimal(0)
        for data in inputs:
            now = data["observedAt"]
            domain.ingest(state, data, now, strategy_runner=runner)
            point = domain.sample(state, now, force=True)
            if point:
                value = Decimal(point["equity"])
                peak = max(peak, value)
                drawdown = max(drawdown, (peak - value) / peak * 100)
        last = state["samples"][-1] if state["samples"] else None
        results.append(
            {
                "strategy_ref": ref,
                "valued": last is not None,
                "profit": last["profit"] if last else None,
                "max_drawdown_percent": str(drawdown) if last else None,
                "fills": len(state["fills"]),
                "open_positions": len(state["positions"]),
                "errors": sum(e["code"] == "strategy_execution_failed" for e in state["events"]),
            }
        )
    return {
        "id": uuid.uuid4().hex,
        "kind": "diagnostic_replay",
        "strategy_ref": target_ref,
        "session_id": original["id"],
        "source": original["source"],
        "input_count": len(inputs),
        "first_input": inputs[0]["id"] if inputs else None,
        "last_input": inputs[-1]["id"] if inputs else None,
        "source_digest": modules[target_ref]["digest"],
        "results": results,
        "profitability_validated": False,
        "limitations": (
            "Current universe on past inputs, flat start, commission only; "
            "not out-of-sample evidence."
        ),
    }
