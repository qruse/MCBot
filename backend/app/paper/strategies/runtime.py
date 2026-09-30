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


def validate_signal(value, context):
    try:
        signal = Signal.model_validate(value)
        if not set(signal.exits) <= {p["symbol"] for p in context["positions"]}:
            raise ValueError()
        if signal.entry_group is not None:
            if not context["can_enter"] or signal.entry_group not in context["groups"]:
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
        return signal.model_dump(mode="json")
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
