"""Run immutable strategy source with a deadline and validate all resulting intents."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from app.paper.strategies import builtin
from app.paper.strategies.contracts import Signal

BUILTIN_SOURCE = Path(builtin.__file__).read_text(encoding="utf-8")
CASH_SOURCE = 'def decide(context):\n    return {"reason": "Cash policy."}\n'
BUILTINS = {"theme-top3-v1": BUILTIN_SOURCE, "cash-v1": CASH_SOURCE}
TIMEOUT_SECONDS = 2


class StrategyError(ValueError):
    pass


def digest(source):
    return hashlib.sha256(source.encode()).hexdigest()


def prepare_context(context, protocol_version=1):
    """Adapt immutable registered versions without reinterpreting their group contract."""
    adapted = deepcopy(context)
    adapted["protocol_version"] = protocol_version
    if adapted["data"]["market"] == "GLOBAL" and protocol_version < 5:
        if adapted["can_enter"]:
            raise StrategyError("global_protocol_required")
        market = adapted.get("active_market")
        if market not in ("KR", "US"):
            raise StrategyError("legacy_market_required")
        adapted["data"] = deepcopy(adapted["data"]["markets"][market])
        adapted["groups"] = {k: [s.split(":", 1)[1] for s in v if s.startswith(market + ":")]
                             for k, v in adapted["groups"].items()}
        for field in ("candidate_ready", "minute_ready"):
            adapted[field] = [s.split(":", 1)[1] for s in adapted[field]
                              if s.startswith(market + ":")]
        adapted["active_symbols"] = [p["symbol"] for p in adapted["positions"]]
    if protocol_version < 3:
        adapted.pop("portfolio", None)
        adapted.pop("portfolio_runtime", None)
    if protocol_version == 1:
        adapted["groups"] = {
            name: members for name, members in adapted["groups"].items() if len(members) == 3
        }
    return adapted


def validate_signal(value, context):
    try:
        protocol = context.get("protocol_version", 1)
        plan = context.get("portfolio") or {}
        permitted_targets = {"CASH"} | {s for g in context["groups"].values() for s in g}
        if protocol >= 4:
            permitted_targets.update((f"{item['market']}:{item['symbol']}" if protocol == 5
                                      else item["symbol"]) for item in plan.get("retirements", []))
        signal = Signal.model_validate({"rotate": False, **value} if protocol >= 3 else value)
        if protocol >= 3 and (
            signal.entry_group is not None or signal.weights or signal.exits or signal.rotate
        ):
            raise ValueError()
        if signal.target_weights:
            if (
                protocol not in (3, 4, 5)
                or not context["can_enter"]
                or signal.entry_group is not None
                or signal.weights
                or signal.exits
                or signal.rotate
                or signal.target_weights
                != {
                    k: Decimal(v)
                    for k, v in (context.get("portfolio") or {}).get("target_weights", {}).items()
                }
                or set(signal.target_weights) != permitted_targets
                or any(
                    not w.is_finite()
                    or w < 0
                    or w > 1
                    or w.as_tuple().exponent < -8
                    or protocol == 3
                    and (w == 0 or w == 1)
                    for w in signal.target_weights.values()
                )
                or "CASH" not in signal.target_weights
                or signal.target_weights["CASH"] < 0
                or protocol == 3
                and signal.target_weights["CASH"] == 0
                or sum(signal.target_weights.values()) != Decimal(1)
            ):
                raise ValueError()
        if not set(signal.exits) <= {p["symbol"] for p in context["positions"]}:
            raise ValueError()
        if signal.entry_group is not None:
            if not context["can_enter"] or signal.entry_group not in context["groups"]:
                raise ValueError()
            if (
                context.get("protocol_version", 1) == 2
                and len(context["groups"][signal.entry_group]) < 3
                and not signal.weights
            ):
                raise ValueError()
        if signal.weights:
            if signal.entry_group is None:
                raise ValueError()
            if not set(signal.weights) <= set(context["groups"][signal.entry_group]):
                raise ValueError()
            if any(
                not w.is_finite() or w <= 0 or w > 1 or w.as_tuple().exponent < -8
                for w in signal.weights.values()
            ):
                raise ValueError()
            if sum(signal.weights.values()) != Decimal(1):
                raise ValueError()
        result = signal.model_dump(mode="json")
        if context.get("protocol_version", 1) < 3:
            result.pop("target_weights")
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise StrategyError("invalid_strategy_output") from exc


def execute(source, context):
    if source == BUILTIN_SOURCE:
        return validate_signal(builtin.decide(deepcopy(context)), context)
    if source == CASH_SOURCE:
        return validate_signal({}, context)
    # No inherited API keys, HOME, PYTHONPATH, cwd or site packages. This is crash containment,
    # not a claim that same-user Python cannot access absolute paths or the network.
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    with tempfile.TemporaryDirectory(prefix="mcbot-strategy-") as directory:
        try:
            with tempfile.TemporaryFile() as output:
                result = subprocess.run(
                    [sys.executable, "-I", "-S", str(Path(__file__).with_name("worker.py"))],
                    input=json.dumps({"source": source, "context": context}).encode(),
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    timeout=TIMEOUT_SECONDS,
                    cwd=directory,
                    env=environment,
                    check=False,
                )
                if result.returncode or output.tell() > 32768:
                    raise StrategyError("strategy_execution_failed")
                output.seek(0)
                value = json.loads(output.read())
        except subprocess.TimeoutExpired as exc:
            raise StrategyError("strategy_timeout") from exc
        except (OSError, ValueError) as exc:
            if isinstance(exc, StrategyError):
                raise
            raise StrategyError("strategy_execution_failed") from exc
    return validate_signal(value, context)
