"""Whole-share paper allocation; execution remains behind common admission and risk gates."""

from decimal import Decimal

from app.paper import domain

D = Decimal
HOUR = 3600000


def valuation(s, data, now, require_targets=True):
    plan = (s.get("policy") or {}).get("portfolio")
    if not plan or (not data and s["positions"]):
        return None
    targets = set(plan["target_weights"]) - {"CASH"}
    symbols = targets.copy() if require_targets else set()
    global_mode = s["config"]["market"] == "GLOBAL"
    if global_mode:
        from app.paper.global_account import cash_value, lot_key, valued_price
    lot_symbols = {lot_key(s, p) if global_mode else p["symbol"] for p in s["positions"]}
    symbols.update(lot_symbols)
    prices = {symbol: valued_price(s, symbol, data, now) if global_mode
              else domain.price(symbol, data, now) for symbol in symbols}
    if any(prices[k] is None for k in (lot_symbols if global_mode else symbols)):
        return None
    quantities = {symbol: 0 for symbol in targets | symbols}
    for lot in s["positions"]:
        quantities[lot_key(s, lot) if global_mode else lot["symbol"]] += lot["shares"]
    values = {
        symbol: prices[symbol] * quantity if quantity else D(0)
        for symbol, quantity in quantities.items()
    }
    values["CASH"] = cash_value(s, now) if global_mode else D(s["cash"])
    if values["CASH"] is None:
        return None
    return prices, quantities, values, sum(values.values())


def status(s, now):
    plan = (s.get("policy") or {}).get("portfolio")
    if not plan or (s["config"]["market"] == "GLOBAL"
                    and (s.get("policy") or {}).get("schema_version") != 8):
        return None
    value = valuation(s, s.get("latest"), now, require_targets=False)
    runtime = s.get("portfolioRuntime", {})
    rows = []
    adaptive = plan.get("mode") == "adaptive"
    from app.paper.global_account import candidate
    global_mode = s["config"]["market"] == "GLOBAL"
    themes = {
        (candidate(s, item) if global_mode else item["symbol"]): group["name"]
        for group in s.get("candidateGroups", [])
        for item in group["candidates"]
    }
    pinned = set(domain.standing_symbols(s))
    retired = {candidate(s, item) if global_mode else item["symbol"]
               for item in plan.get("retirements", [])}
    for symbol, weight in plan["target_weights"].items():
        target = D(weight)
        actual = value[2].get(symbol, D(0)) if value else D(s["cash"]) if symbol == "CASH" else None
        nav = value[3] if value else None
        rows.append(
            {
                "symbol": symbol,
                "targetPercent": str(target * 100),
                "actualPercent": str(actual / nav * 100) if nav else None,
                "actualAmount": str(actual) if actual is not None else None,
                "targetAmount": str(nav * target) if nav else None,
                "theme": themes.get(symbol),
                "standing": symbol in pinned,
                "retiring": symbol in retired,
            }
        )
    return {
        "rows": rows,
        "mode": "adaptive" if adaptive else "allocation",
        "nav": str(value[3]) if value else None,
        "driftPercent": plan["drift_percent"],
        "minimumTradeKrw": plan["minimum_trade_krw"],
        "maxTurnoverPercent": plan["max_turnover_percent"],
        "lastRebalancedAt": runtime.get("last_at"),
        "nextRebalanceAt": (runtime["last_slot"] + 1) * HOUR
        if runtime.get("last_slot") is not None
        else now,
        "reason": runtime.get("reason", "allocation_pending"),
    }


def orders(s, data, now):
    value = valuation(s, data, now)
    if value is None:
        return []
    prices, quantities, values, nav = value
    plan = s["policy"]["portfolio"]
    weights = {k: D(v) for k, v in plan["target_weights"].items()}
    runtime = s.get("portfolioRuntime", {})
    initial = runtime.get("last_slot") is None and not s["positions"]
    if not initial and max(
        abs(values.get(k, D(0)) / nav - w) * 100 for k, w in weights.items()
    ) < D(plan["drift_percent"]):
        return []
    desired = {k: int(nav * w / prices[k]) for k, w in weights.items()
               if k != "CASH" and prices.get(k) is not None}
    # No liquidation of an omitted holding is implicit in a universe change.
    minimum = D(0) if initial else D(plan["minimum_trade_krw"])
    budget = nav if initial else nav * D(plan["max_turnover_percent"]) / 100
    global_mode = data["market"] == "GLOBAL"
    if global_mode:
        from app.paper.global_account import executable, fx_rate, split
    cash, invested = values["CASH"], nav - values["CASH"]
    cap = D(s["policy"]["max_exposure_percent"]) / 100
    result = []
    for side in ("sell", "buy"):
        for symbol in desired:
            market = split(symbol)[0] if global_mode else data["market"]
            rate = domain.fee(market)
            if global_mode and (
                executable(symbol, data, now) is None
                or data["markets"][market]["marketClose"] - now <= domain.closing_window(market)
                or market in s.get("marketEntryBlocks", {})
                or D(s["cashBalances"]["USD"]) and fx_rate(data, now) is None
            ):
                continue
            change = desired[symbol] - quantities[symbol]
            if (side == "sell" and change >= 0) or (side == "buy" and change <= 0):
                continue
            if side == "buy" and (
                symbol in s["policy"]["entry_blocks"]
                or runtime.get("risk_blocks", {}).get(symbol, 0) > now
            ):
                continue
            p = prices[symbol]
            count = min(abs(change), int(budget / p))
            if side == "buy":
                # Reserve and exposure use NAV after modeled commissions, including this buy.
                room = min(
                    (cash - weights["CASH"] * nav) / (1 + rate * (1 - weights["CASH"])),
                    (cap * nav - invested) / (1 + cap * rate),
                )
                count = min(count, max(0, int(room / p)))
            gross = p * count
            if count <= 0 or gross < minimum:
                continue
            result.append({"symbol": symbol, "side": side, "shares": count})
            budget -= gross
            nav -= gross * rate
            cash += gross * (1 - rate) if side == "sell" else -gross * (1 + rate)
            invested += -gross if side == "sell" else gross
    return result


def purchase(s, data, now, order):
    if s["config"]["market"] == "GLOBAL":
        from app.paper.global_account import purchase as global_purchase
        return global_purchase(s, data, now, order)
    symbol, count = order["symbol"], order["shares"]
    p = domain.price(symbol, data, now)
    rate = domain.fee(data["market"])
    gross, commission = p * count, p * count * rate
    policy = s["policy"]
    fill_id = f"{s['id']}-{len(s['fills']) + 1}"
    lot = {
        "symbol": symbol,
        "name": data["securities"][symbol].get("name", symbol),
        "shares": count,
        "entryPrice": str(p),
        "entryFx": str(data["fx"]["rate"] if data["market"] == "US" else 1),
        "entryFee": str(commission),
        "entryCost": str(gross + commission),
        "entrySourceTime": data["quotes"][symbol]["sourceTime"],
        "policyVersion": s["policyVersion"],
        "proposalId": policy["proposal_id"],
        "entryId": fill_id,
        "strategyRef": domain.policy_ref(policy),
        "strategyDigest": policy.get("strategy_digest"),
    }
    s["cash"] = str(D(s["cash"]) - gross - commission)
    s["positions"].append(lot)
    s["fills"].append(
        {
            "id": fill_id,
            "snapshotId": data["id"],
            "timestamp": now,
            "symbol": symbol,
            "side": "buy",
            "shares": count,
            "priceKrw": str(p),
            "fx": lot["entryFx"],
            "fee": str(commission),
            "gross": str(gross),
            "reason": "portfolio_rebalance",
            "netProfit": None,
            **{
                k: lot[k]
                for k in ("policyVersion", "proposalId", "entryId", "strategyRef", "strategyDigest")
            },
        }
    )
    domain.event(s, "portfolio_rebalance", now, "buy", symbol)


def rebalance(s, data, now, runner):
    runtime = s.setdefault("portfolioRuntime", {"risk_blocks": {}})
    slot = now // HOUR
    if runtime.get("last_slot", -1) >= slot:
        runtime["reason"] = "hourly_limit"
        s["pending"] = None
        return
    signal = domain.run_strategy(
        s,
        domain.policy_ref(s["policy"]),
        s["policy"].get("strategy_digest"),
        domain.strategy_context(s, data, now, domain.candidate_groups(s), [], True),
        now,
        runner,
    )
    if not signal or not signal.get("target_weights"):
        runtime["reason"] = "allocation_hold"
        s["pending"] = None
        return
    planned = orders(s, data, now)
    if not planned:
        runtime["reason"] = "within_band"
        s["pending"] = None
        return
    pending = s["pending"]
    if (
        not pending
        or pending.get("kind") != "portfolio"
        or pending["version"] != s["policyVersion"]
    ):
        s["pending"] = {"kind": "portfolio", "at": now, "version": s["policyVersion"]}
        runtime["reason"] = "later_quote_pending"
        return
    # Reprice the approved targets only after all involved quotes advance beyond the signal.
    if any(data["quotes"][o["symbol"]]["sourceTime"] <= pending["at"] for o in planned):
        runtime["reason"] = "later_quote_pending"
        return
    for order in planned:
        if order["side"] == "buy":
            purchase(s, data, now, order)
        else:
            remaining = order["shares"]
            for lot in s["positions"][:]:
                from app.paper.global_account import candidate, lot_key
                global_mode = s["config"]["market"] == "GLOBAL"
                identity = lot_key(s, lot) if global_mode else lot["symbol"]
                if identity == order["symbol"] and remaining:
                    count = min(remaining, lot["shares"])
                    reason = (
                        "portfolio_rotation"
                        if any(
                            (candidate(s, item) if global_mode else item["symbol"])
                            == order["symbol"]
                            for item in s["policy"]["portfolio"].get("retirements", [])
                        )
                        else "portfolio_rebalance"
                    )
                    if domain.sell(s, lot, data, now, reason, count):
                        remaining -= count
    runtime.update(last_slot=slot, last_at=now, reason="rebalanced")
    s["activeSymbols"] = list(dict.fromkeys(p["symbol"] for p in s["positions"]))
    s["activeTheme"] = "portfolio"
    s["pending"] = None
