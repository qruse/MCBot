"""Paper accounting and common risk controls with an injected strategy execution port."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation

from app.paper.contracts import THEMES, Settings, standing_groups
from app.paper.strategies.builtin import long_score as long_score
from app.paper.strategies.builtin import trend as trend
from app.paper.strategies.runtime import BUILTINS, StrategyError, digest, execute

D = Decimal


def candidate_groups(state):
    if state.get("isBenchmark"):
        return THEMES[state["config"]["market"]]
    if "candidateGroups" in state:
        groups = {
            group["group_id"]: [c["symbol"] for c in group["candidates"]]
            for group in state["candidateGroups"]
        }
    else:
        # Legacy plans retain their own admission list; pinned monitoring is still visible.
        groups = dict(THEMES[state["config"]["market"]]) if state.get("policy") else {}
    groups.update(
        {
            g["group_id"]: [c["symbol"] for c in g["candidates"]]
            for g in state.get("standingGroups", [])
        }
    )
    return groups


def candidate_symbols(state):
    return list(
        dict.fromkeys(symbol for group in candidate_groups(state).values() for symbol in group)
    )


def standing_symbols(state):
    return [c["symbol"] for group in state.get("standingGroups", []) for c in group["candidates"]]


def collection_symbols(state, now):
    # Pinned monitoring survives proposal expiry, but never bypasses the session's Start gate.
    current = (
        candidate_symbols(state) if (state.get("candidateExpiresAt") or float("inf")) > now else []
    )
    return list(dict.fromkeys([*standing_symbols(state), *current]))


def protected_symbols(state):
    return (
        list(
            dict.fromkeys(
                [*[p["symbol"] for p in state["positions"]], *state.get("activeSymbols", [])]
            )
        )
        if state["positions"]
        else []
    )


def policy_ref(policy):
    return (
        f"{policy['playbook_id']}@{policy.get('strategy_version', 1)}"
        if policy
        else "theme-top3-v1@1"
    )


def strategy_context(s, data, now, groups, positions, can_enter):
    symbols = set(data["quotes"]) | {p["symbol"] for p in positions}
    return {
        "protocol_version": 1,
        "now": now,
        "data": deepcopy(data),
        "groups": deepcopy(groups),
        "positions": deepcopy(positions),
        "active_symbols": s.get("activeSymbols", [])[:],
        "cash": s["cash"],
        "capital": s["config"]["capital"],
        "can_enter": can_enter,
        "candidate_ready": sorted(symbol for symbol in symbols if ready(symbol, data, now)),
        "minute_ready": sorted(
            symbol for symbol in symbols if history_ready(symbol, "minute", data, now)
        ),
    }


def run_strategy(s, ref, expected_digest, context, now, runner):
    try:
        if runner:
            result = runner(ref, context, expected_digest)
        else:
            name, version = ref.rsplit("@", 1)
            if name not in BUILTINS or version != "1":
                raise StrategyError("strategy_not_registered")
            if expected_digest and digest(BUILTINS[name]) != expected_digest:
                raise StrategyError("strategy_digest_mismatch")
            result = execute(BUILTINS[name], context)
        s["strategyDecision"] = {"ref": ref, "timestamp": now, **result}
        return result
    except (StrategyError, ValueError, TypeError):
        s["strategyError"] = "strategy_execution_failed"
        event(s, "strategy_execution_failed", now, "risk")
        s["events"][-1]["strategyRef"] = ref
        s["pending"] = None
        return None


def instrument_issue(symbol, data, now):
    item = data.get("securities", {}).get(symbol)
    if not item:
        return "instrument_unverified"
    markets = ("KOSPI", "KOSDAQ") if data["market"] == "KR" else ("NYSE", "NASDAQ", "AMEX")
    detail = item.get("koreanMarketDetail") or {}
    if (
        item.get("market") not in markets
        or item.get("currency") != ("KRW" if data["market"] == "KR" else "USD")
        or item.get("status") != "ACTIVE"
        or item.get("securityType") not in ("STOCK", "FOREIGN_STOCK", "ETF", "FOREIGN_ETF")
        or detail.get("liquidationTrading") is not False
        and data["market"] == "KR"
        or detail.get("krxTradingSuspended") is not False
        and data["market"] == "KR"
    ):
        return "instrument_ineligible"
    return None if fresh(item.get("receivedAt"), now, 360000) else "instrument_unverified"


def candidate_issue(symbol, data, now):
    issue = instrument_issue(symbol, data, now)
    if issue:
        return issue
    if price(symbol, data, now) is None:
        return "candidate_quote_unavailable"
    if not (
        history_ready(symbol, "minute", data, now) and history_ready(symbol, "daily", data, now)
    ):
        return "candidate_history_pending"
    return (
        "candidate_change_pending"
        if decimal(data["quotes"][symbol].get("changePercent")) is None
        else None
    )


def decimal(value):
    try:
        result = D(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def positive(value):
    result = decimal(value)
    return result if result is not None and result > 0 else None


def fresh(value, now, age):
    return isinstance(value, (int, float)) and 0 < value <= now and now - value <= age


def price(symbol, data, now):
    quote = data["quotes"].get(symbol)
    if not quote or not positive(quote["price"]):
        return None
    known = data.get("securities", {}).get(symbol)
    if known and instrument_issue(symbol, data, now) == "instrument_ineligible":
        return None
    if quote["currency"] != ("KRW" if data["market"] == "KR" else "USD"):
        return None
    if not all(fresh(quote[k], now, 90000) for k in ("sourceTime", "receivedAt")):
        return None
    rate = D(1)
    if data["market"] == "US":
        fx = data.get("fx")
        if (
            not fx
            or not positive(fx["rate"])
            or not fresh(fx["receivedAt"], now, 360000)
            or not 0 < fx["validFrom"] <= now <= fx["validUntil"]
        ):
            return None
        rate = D(str(fx["rate"]))
    return D(str(quote["price"])) * rate


def history_ready(symbol, interval, data, now):
    history = data[interval].get(symbol)
    minimum, age = (26, 1200000) if interval == "minute" else (80, 4200000)
    if not history or len(history["candles"]) < minimum:
        return False
    if not fresh(history["receivedAt"], now, age):
        return False
    previous = 0
    for bar in history["candles"]:
        if (
            not positive(bar["close"])
            or not bar["complete"]
            or not previous < bar["closedAt"] <= now
        ):
            return False
        previous = bar["closedAt"]
    return (
        now - previous <= age
        if interval == "minute"
        else 0 < data["expectedDailyClose"] <= previous
    )


def ready(symbol, data, now):
    return candidate_issue(symbol, data, now) is None


def fee(market):
    return D(".00015") if market == "KR" else D(".001")


def mark(position, data, now):
    p = price(position["symbol"], data, now)
    return None if p is None else p * position["shares"] * (1 - fee(data["market"]))


def equity(state, data, now):
    values = [mark(p, data, now) for p in state["positions"]]
    return None if any(v is None for v in values) else D(state["cash"]) + sum(values)


def create(settings: Settings, session_id: str):
    return {
        "id": session_id,
        "version": 0,
        "evaluatedAt": 0,
        "config": {
            "market": settings.market,
            "capital": str(settings.capital),
            "stopPercent": 2,
            "sidecarPercent": 5,
        },
        "source": settings.source,
        "mode": settings.mode,
        "lifecycle": "idle",
        "condition": "warming_up",
        "reason": "Waiting for explicit Start.",
        "baseline": None,
        "cash": str(settings.capital),
        "positions": [],
        "fills": [],
        "events": [],
        "samples": [],
        "gaps": [],
        "segment": 0,
        "ready": 0,
        "total": 0,
        "candidateGroups": [],
        "standingGroups": standing_groups(settings.market),
        "candidateChecks": {},
        "candidateProposalId": None,
        "candidateExpiresAt": None,
        "activeSymbols": [],
        "activeTheme": None,
        "latest": None,
        "pending": None,
        "lastDecision": None,
        "entriesPaused": False,
        "leaseUntil": None,
        "policyVersion": 0,
        "policy": None,
        "strategyError": None,
        "strategyDecision": None,
        "entryBlock": "awaiting_review",
        "lastSampleAt": 0,
        "feePolicy": "commission-only-v1",
        "costsComplete": False,
    }


def event(s, code, now, kind="decision", symbol=None):
    s["events"].append(
        {
            "id": len(s["events"]) + 1,
            "timestamp": now,
            "snapshotId": s["latest"]["id"] if s["latest"] else None,
            "kind": kind,
            "code": code,
            "text": code,
            "symbol": symbol,
        }
    )


def gap(s, reason, now):
    if s["gaps"] and s["gaps"][-1]["end"] is None:
        if s["gaps"][-1]["reason"] == reason:
            return
        s["gaps"][-1]["end"] = now
    s["segment"] += 1
    s["gaps"].append({"start": now, "end": None, "reason": reason})
    event(s, reason, now, "data")


def block(s, now):
    policy = s["policy"]
    if s["entriesPaused"]:
        return "entries_paused"
    if s["mode"] == "observer":
        return "observer"
    if not policy:
        return "awaiting_review"
    if not policy["valid_from"] <= now < policy["expires_at"]:
        return "policy_expired"
    if policy["playbook_id"] == "cash-v1":
        return "cash_policy"
    return "none"


def assess(s, now):
    data = s["latest"]
    s["evaluatedAt"] = now
    s["entryBlock"] = block(s, now)
    selected = candidate_symbols(s)
    s["candidateChecks"] = {
        symbol: candidate_issue(symbol, data, now) if data else "instrument_unverified"
        for symbol in selected
    }
    s["total"] = len(selected)
    s["ready"] = sum(issue is None for issue in s["candidateChecks"].values())
    if not data:
        s["condition"] = "warming_up"
    elif data["provider"] != "ready":
        s["condition"] = (
            "authentication_error"
            if data["provider"] == "authentication_error"
            else "provider_cooldown"
        )
    elif not data["marketOpen"] or now >= data["marketClose"]:
        s["condition"] = "market_closed"
    elif equity(s, data, now) is None:
        s["condition"] = "data_stale"
    elif s["ready"] < s["total"]:
        s["condition"] = "warming_up"
    else:
        s["condition"] = "ready"
    s["reason"] = s["condition"]


def sell(s, position, data, now, reason):
    value = mark(position, data, now)
    # Only a new source price after entry may liquidate a holding.
    q = data["quotes"].get(position["symbol"], {})
    if value is None or q.get("sourceTime", 0) <= position["entrySourceTime"]:
        event(s, "risk_unavailable", now, "risk", position["symbol"])
        return False
    p = price(position["symbol"], data, now)
    gross = p * position["shares"]
    s["cash"] = str(D(s["cash"]) + value)
    s["positions"].remove(position)
    s["fills"].append(
        {
            "id": f"{s['id']}-{len(s['fills']) + 1}",
            "snapshotId": data["id"],
            "timestamp": now,
            "symbol": position["symbol"],
            "side": "sell",
            "shares": position["shares"],
            "priceKrw": str(p),
            "fx": str(data["fx"]["rate"] if data["market"] == "US" else 1),
            "gross": str(gross),
            "fee": str(gross - value),
            "reason": reason,
            "netProfit": str(value - D(position["entryCost"])),
            "policyVersion": position["policyVersion"],
            "proposalId": position["proposalId"],
            "entryId": position["entryId"],
            "strategyRef": position.get("strategyRef", "theme-top3-v1@1"),
            "strategyDigest": position.get("strategyDigest"),
        }
    )
    event(s, reason, now, "sell", position["symbol"])
    return True


def buy(s, data, now, pending):
    weights = pending.get("weights", {})
    group = list(weights) if weights else candidate_groups(s)[pending["theme"]]
    policy = s["policy"]
    exposure = D(str(policy["max_exposure_percent"])) / 100 if policy else D(1)
    budget = D(s["cash"]) * exposure
    rate = fee(data["market"])
    drafts = []
    for symbol in group:
        p = price(symbol, data, now)
        # Fill after the decision, using a later observed trade; never the signal's close.
        if p is None or data["quotes"][symbol]["sourceTime"] <= pending["at"]:
            return False
        unit = p * (1 + rate)
        weight = D(weights[symbol]) if weights else D(1) / 3
        drafts.append(
            {
                "symbol": symbol,
                "shares": int(budget * weight / unit),
                "price": p,
                "unit": unit,
                "weight": weight,
            }
        )
    remaining = budget - sum(x["shares"] * x["unit"] for x in drafts)
    for _ in range(1000):
        affordable = [x for x in drafts if x["unit"] <= remaining]
        if not affordable:
            break
        item = min(affordable, key=lambda x: (x["shares"] * x["unit"] / x["weight"], x["price"]))
        item["shares"] += 1
        remaining -= item["unit"]
    for item in drafts:
        if not item["shares"]:
            continue
        symbol, p, shares = item["symbol"], item["price"], item["shares"]
        cost = shares * item["unit"]
        fill_id = f"{s['id']}-{len(s['fills']) + 1}"
        position = {
            "symbol": symbol,
            "name": data.get("securities", {}).get(symbol, {}).get("name", symbol),
            "shares": shares,
            "entryPrice": str(p),
            "entryFx": str(data["fx"]["rate"] if data["market"] == "US" else 1),
            "entryFee": str(shares * p * rate),
            "entryCost": str(cost),
            "entrySourceTime": data["quotes"][symbol]["sourceTime"],
            "policyVersion": s["policyVersion"],
            "proposalId": policy["proposal_id"] if policy else "baseline",
            "entryId": fill_id,
            "strategyRef": policy_ref(policy),
            "strategyDigest": policy.get("strategy_digest") if policy else None,
        }
        s["positions"].append(position)
        s["cash"] = str(D(s["cash"]) - cost)
        s["fills"].append(
            {
                "id": fill_id,
                "snapshotId": data["id"],
                "timestamp": now,
                "symbol": symbol,
                "side": "buy",
                "shares": shares,
                "priceKrw": str(p),
                "fx": position["entryFx"],
                "fee": position["entryFee"],
                "gross": str(shares * p),
                "reason": "theme_entry",
                "netProfit": None,
                "policyVersion": s["policyVersion"],
                "proposalId": position["proposalId"],
                "entryId": fill_id,
                "strategyRef": position["strategyRef"],
                "strategyDigest": position["strategyDigest"],
            }
        )
        event(s, "theme_entry", now, "buy", symbol)
    s["activeTheme"] = pending["theme"]
    s["activeSymbols"] = candidate_groups(s)[pending["theme"]][:]
    return True


def ingest(s, data, now, baseline=False, strategy_runner=None):
    if (
        data["market"] != s["config"]["market"]
        or data["observedAt"] > now
        or s["latest"]
        and data["observedAt"] < s["latest"]["observedAt"]
    ):
        return
    s["latest"] = deepcopy(data)
    assess(s, now)
    if s["lifecycle"] == "preparing" and s["condition"] == "ready":
        s["baseline"] = s["cash"]
        s["lifecycle"] = "running"
        event(s, "prepared", now, "command")
        sample(s, now)
    if s["lifecycle"] != "running" or s["lastDecision"] == data["id"]:
        return
    s["lastDecision"] = data["id"]
    s["strategyError"] = None
    if not data["marketOpen"] or now >= data["marketClose"]:
        return
    marks = [mark(p, data, now) for p in s["positions"]]
    complete = all(v is not None for v in marks)
    sidecar = (
        bool(marks)
        and complete
        and sum(marks) <= sum(D(p["entryCost"]) for p in s["positions"]) * D(".95")
    )
    exited = False
    for position, value in zip(s["positions"][:], marks, strict=True):
        symbol = position["symbol"]
        reason = None
        if value is None:
            event(s, "risk_unavailable", now, "risk", symbol)
            continue
        if sidecar:
            reason = "sidecar_halt"
        elif data["closingSoon"] or data["marketClose"] - now <= 300000:
            reason = "closing_exit"
        elif value <= D(position["entryCost"]) * D(".98"):
            reason = "position_stop"
        if reason:
            exited = sell(s, position, data, now, reason) or exited
    if sidecar:
        s["pending"] = None
        s["entriesPaused"] = True
        # Continue protection if a position could not fill; never claim a completed halt exit.
        if not s["positions"]:
            sample(s, now, force=True)
            s["lifecycle"] = "halted"
            gap(s, "sidecar_halt", now)
        return
    groups = candidate_groups(s)
    group = s.get("activeSymbols") or THEMES[data["market"]].get(s["activeTheme"])
    # Open positions keep the code version that admitted them, across later plan changes.
    held_refs = {
        (p.get("strategyRef", "theme-top3-v1@1"), p.get("strategyDigest")) for p in s["positions"]
    }
    for ref, code_digest in sorted(held_refs, key=lambda item: item[0]):
        positions = [p for p in s["positions"] if p.get("strategyRef", "theme-top3-v1@1") == ref]
        context = strategy_context(s, data, now, groups, positions, False)
        context["active_symbols"] = group or []
        signal = run_strategy(s, ref, code_digest, context, now, strategy_runner)
        if signal:
            for p in positions:
                if p["symbol"] in signal["exits"]:
                    exited = sell(s, p, data, now, signal["exits"][p["symbol"]]) or exited
    allowed = baseline or s["entryBlock"] == "none"
    if (
        exited
        or s.get("strategyError")
        or not allowed
        or s["condition"] != "ready"
        or data["marketClose"] - now <= 300000
    ):
        s["pending"] = None
        return
    if s["policy"]:
        # V3 explicitly admits the owner's standing group in addition to the researcher list.
        pinned = standing_symbols(s) if s["policy"].get("schema_version", 1) >= 3 else []
        permitted = (set(s["policy"]["allowed_symbols"]) | set(pinned)) - set(
            s["policy"]["entry_blocks"]
        )
        groups = {name: group for name, group in groups.items() if set(group) <= permitted}
    signal = run_strategy(
        s,
        policy_ref(s["policy"]),
        (s["policy"] or {}).get("strategy_digest"),
        strategy_context(s, data, now, groups, [], True),
        now,
        strategy_runner,
    )
    if signal is None:
        return
    theme = signal["entry_group"]
    if s["positions"]:
        if (
            signal["rotate"]
            and theme
            and (theme != s["activeTheme"] or set(groups[theme]) != set(group or []))
        ):
            for p in s["positions"][:]:
                sell(s, p, data, now, "theme_rotation")
        s["pending"] = None
        return
    pending = s["pending"]
    if (
        pending
        and pending["theme"] == theme
        and pending["version"] == s["policyVersion"]
        and pending.get("weights", {}) == signal["weights"]
    ):
        if buy(s, data, now, pending):
            s["pending"] = None
            return
    s["pending"] = (
        {"theme": theme, "at": now, "version": s["policyVersion"], "weights": signal["weights"]}
        if theme
        else None
    )


def sample(s, now, force=False):
    assess(s, now)
    if s["lifecycle"] != "running" or s["baseline"] is None or not s["latest"]:
        return None
    if not force and now - s["lastSampleAt"] < 5000:
        return None
    data = s["latest"]
    value = equity(s, data, now)
    if value is None or s["condition"] in (
        "market_closed",
        "provider_cooldown",
        "authentication_error",
    ):
        gap(s, s["condition"] if value is not None else "data_stale", now)
        return None
    if s["gaps"] and s["gaps"][-1]["end"] is None:
        s["gaps"][-1]["end"] = now
    profit = value - D(s["baseline"])
    point = {
        "timestamp": now,
        "snapshotId": data["id"],
        "segment": s["segment"],
        "equity": str(value),
        "cash": s["cash"],
        "holdings": len(s["positions"]),
        "profit": str(profit),
        "returnPercent": str(profit / D(s["baseline"]) * 100),
        "priceSourceTime": min(
            (data["quotes"][p["symbol"]]["sourceTime"] for p in s["positions"]), default=None
        ),
        "fxSourceTime": data["fx"]["validFrom"]
        if s["positions"] and data["market"] == "US"
        else None,
    }
    s["samples"].append(point)
    s["lastSampleAt"] = now
    return point
