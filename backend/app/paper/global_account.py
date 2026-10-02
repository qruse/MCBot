"""One cross-market paper ledger; closed marks are valuation data, never executable prices."""

import hashlib
from copy import deepcopy
from decimal import Decimal as D

from app.paper import domain
from app.paper.storage import encode

VALUATION_AGE = 7 * 86400000


def key(market, symbol):
    return f"{market}:{symbol}"


def split(symbol):
    market, raw = symbol.split(":", 1)
    if market not in ("KR", "US") or not raw:
        raise ValueError("invalid_instrument_key")
    return market, raw


def candidate(s, item):
    return key(item.get("market") or s.get("legacyMarket", "KR"), item["symbol"])


def lot_key(s, lot):
    return key(lot.get("market") or s.get("legacyMarket", "KR"), lot["symbol"])


def enable(s, db, now, preserve_holdings=False):
    if (s["lifecycle"] not in ("idle", "paused") or (s["positions"] and not preserve_holdings)
            or s["config"]["market"] == "GLOBAL"):
        raise ValueError("global_requires_stopped_flat_single_market")
    if s.get("sidecarPending"):
        raise ValueError("global_risk_exit_pending")
    market = s["config"]["market"]
    row = db.execute(
        "SELECT payload FROM observations WHERE json_extract(payload,'$.market')=? "
        "AND json_extract(payload,'$.quotes')!='{}' "
        "ORDER BY json_extract(payload,'$.observedAt') DESC LIMIT 1", (market,)).fetchone()
    import json
    last = json.loads(row[0]) if row else s.get("latest")
    marks = {}
    for field in ("displayQuotes", "quotes"):
        for raw, quote in (last or {}).get(field, {}).items():
            if (domain.positive(quote.get("price"))
                    and quote.get("currency") == ("KRW" if market == "KR" else "USD")
                    and domain.fresh(quote.get("sourceTime"), now, VALUATION_AGE)
                    and 0 < quote.get("receivedAt", 0) <= now):
                marks[key(market, raw)] = deepcopy(quote)
    if s["positions"]:
        if (not last or last.get("marketOpen") and now < last.get("marketClose", 0)):
            raise ValueError("global_held_migration_requires_closed_market")
        if any(key(market, p["symbol"]) not in marks for p in s["positions"]):
            raise ValueError("global_held_valuation_unavailable")
    s.update(legacyMarket=market, cashBalances={"KRW": s["cash"], "USD": "0"},
             valuationQuotes=marks, valuationFx=None, fxConversions=[], continuousPaper=True,
             lastOpenCloses={}, marketEntryBlocks={}, pending=None)
    s["config"]["market"] = "GLOBAL"
    from app.paper.contracts import standing_groups
    s["standingGroups"] = standing_groups("GLOBAL")
    if last:
        s["valuationFx"] = deepcopy(last.get("fx"))
        if s["positions"]:
            s["marketEntryBlocks"][market] = "closing_exit_incomplete"
            if s.get("lastOpenClose"):
                s["lastOpenCloses"][market] = s["lastOpenClose"]
    blocks = s.get("portfolioRuntime", {}).get("risk_blocks", {})
    blocks.update({key(market, raw): until for raw, until in list(blocks.items())
                   if ":" not in raw})
    s["latest"] = None  # Native snapshots are collected independently after owner Resume.
    s["leaseUntil"] = now + 86400000


def lifecycle(s, data, now):
    if s["lifecycle"] not in ("preparing", "running"):
        return
    deadlines = s.setdefault("lastOpenCloses", {})
    blocks = s.setdefault("marketEntryBlocks", {})
    for market, item in data["markets"].items():
        if item["marketOpen"]:
            deadlines[market] = item["marketClose"]
        remaining = any(split(lot_key(s, p))[0] == market for p in s["positions"])
        if deadlines.get(market) and now >= deadlines[market] and remaining:
            if market not in blocks:
                domain.event(s, "closing_exit_incomplete", now, "risk", market)
            blocks[market] = "closing_exit_incomplete"
        if not remaining:
            blocks.pop(market, None)
    if s.get("continuousPaper"):
        s["leaseUntil"] = max(s["leaseUntil"] or 0, now + 86400000)


def combine(markets, now, fx=None):
    opened = [v for v in markets.values() if v["marketOpen"]]
    value = {
        "market": "GLOBAL", "markets": deepcopy(markets), "observedAt": now,
        "marketOpen": bool(opened), "marketClose": min(
            (v["marketClose"] for v in opened), default=0),
        "closingSoon": False, "provider": "ready", "fx": deepcopy(fx),
        "quotes": {}, "minute": {}, "daily": {}, "securities": {},
    }
    for market, native in markets.items():
        for field in ("quotes", "minute", "daily", "securities"):
            value[field].update({key(market, k): deepcopy(v) for k, v in native[field].items()})
    if opened and any(v["provider"] != "ready" for v in opened):
        value["provider"] = next(v["provider"] for v in opened if v["provider"] != "ready")
    identity = {k: v for k, v in value.items() if k not in ("observedAt", "markets")}
    identity["markets"] = {m: v["id"] for m, v in markets.items()}
    value["id"] = hashlib.sha256(encode(identity).encode()).hexdigest()
    return value


def native(data, symbol):
    market, raw = split(symbol)
    return data["markets"][market], raw


def fx_rate(data, now):
    fx = (data or {}).get("fx")
    if (not fx or not domain.positive(fx.get("rate"))
            or not domain.fresh(fx.get("receivedAt"), now, 360000)
            or not 0 < fx.get("validFrom", 0) <= now <= fx.get("validUntil", 0)):
        return None
    return D(fx["rate"])


def refresh(s, data, now):
    cache = s.setdefault("valuationQuotes", {})
    for symbol, q in data["quotes"].items():
        market, _ = split(symbol)
        if (domain.positive(q.get("price"))
                and q.get("currency") == ("KRW" if market == "KR" else "USD")
                and 0 < q.get("sourceTime", 0) <= now
                and 0 < q.get("receivedAt", 0) <= now
                and q["sourceTime"] >= cache.get(symbol, {}).get("sourceTime", 0)):
            cache[symbol] = deepcopy(q)
    if fx_rate(data, now) is not None:
        s["valuationFx"] = deepcopy(data["fx"])
    cash = cash_value(s, now)
    if cash is not None:
        s["cash"] = str(cash)


def valuation_fx(s, now):
    fx = s.get("valuationFx")
    return (D(fx["rate"]) if fx and domain.positive(fx.get("rate"))
            and domain.fresh(fx.get("validFrom"), now, VALUATION_AGE) else None)


def cash_value(s, now):
    balances = s["cashBalances"]
    dollars = D(balances["USD"])
    rate = valuation_fx(s, now)
    return None if dollars and rate is None else D(balances["KRW"]) + dollars * (rate or D(0))


def valued_price(s, symbol, data, now):
    native_data, raw = native(data, symbol)
    if native_data["marketOpen"]:
        native_data = {**native_data, "fx": data.get("fx")}
        return domain.price(raw, native_data, now)
    q = s.get("valuationQuotes", {}).get(symbol)
    if not q or not domain.fresh(q.get("sourceTime"), now, VALUATION_AGE):
        return None
    rate = D(1) if native_data["market"] == "KR" else valuation_fx(s, now)
    return D(q["price"]) * rate if rate is not None else None


def executable(symbol, data, now):
    item, raw = native(data, symbol)
    if not item["marketOpen"] or now >= item["marketClose"]:
        return None
    return domain.price(raw, {**item, "fx": data.get("fx")}, now)


def mark(s, lot, data, now):
    symbol = lot_key(s, lot)
    p = valued_price(s, symbol, data, now)
    return None if p is None else p * lot["shares"] * (1 - domain.fee(split(symbol)[0]))


def equity(s, data, now):
    if not data:
        return None
    cash = cash_value(s, now)
    marks = [mark(s, lot, data, now) for lot in s["positions"]]
    return None if cash is None or any(p is None for p in marks) else cash + sum(marks)


def fund(s, currency, amount, data, now):
    balances = s["cashBalances"]
    current = D(balances[currency])
    if amount <= current:
        return True
    rate = fx_rate(data, now)
    if rate is None:
        return False
    other = "USD" if currency == "KRW" else "KRW"
    shortage = amount - current
    debit = shortage / rate if currency == "KRW" else shortage * rate
    if debit > D(balances[other]):
        return False
    balances[other] = str(D(balances[other]) - debit)
    balances[currency] = str(amount)
    s.setdefault("fxConversions", []).append({
        "id": len(s.get("fxConversions", [])) + 1, "timestamp": now,
        "from": other, "to": currency, "debit": str(debit), "credit": str(shortage),
        "rate": str(rate), "sourceTime": data["fx"]["validFrom"],
        "model": "reference-rate-no-spread", "snapshotId": data["id"],
    })
    return True


def purchase(s, data, now, order):
    symbol, count = order["symbol"], order["shares"]
    market, raw = split(symbol)
    p = executable(symbol, data, now)
    if p is None or count <= 0:
        return False
    quote = data["quotes"][symbol]
    native_price = D(quote["price"])
    rate = p / native_price
    commission = native_price * count * domain.fee(market)
    currency = quote["currency"]
    if not fund(s, currency, native_price * count + commission, data, now):
        return False
    s["cashBalances"][currency] = str(
        D(s["cashBalances"][currency]) - native_price * count - commission)
    policy = s["policy"]
    fill_id = f"{s['id']}-{len(s['fills']) + 1}"
    lot = {
        "market": market, "symbol": raw, "instrumentKey": symbol,
        "name": data["securities"][symbol].get("name", raw), "shares": count,
        "entryPrice": str(p), "entryNativePrice": str(native_price), "currency": currency,
        "entryFx": str(rate), "entryFee": str(commission * rate),
        "entryCost": str(p * count + commission * rate),
        "entrySourceTime": quote["sourceTime"], "policyVersion": s["policyVersion"],
        "proposalId": policy["proposal_id"], "entryId": fill_id,
        "strategyRef": domain.policy_ref(policy), "strategyDigest": policy["strategy_digest"],
    }
    s["positions"].append(lot)
    s["fills"].append({
        "id": fill_id, "snapshotId": data["id"], "timestamp": now, "market": market,
        "symbol": raw, "instrumentKey": symbol, "currency": currency, "side": "buy",
        "shares": count, "priceKrw": str(p), "nativePrice": str(native_price),
        "fx": str(rate), "nativeFee": str(commission), "fee": lot["entryFee"],
        "gross": str(p * count), "reason": "portfolio_rebalance", "netProfit": None,
        **{k: lot[k] for k in ("policyVersion", "proposalId", "entryId", "strategyRef",
                              "strategyDigest")},
    })
    refresh(s, data, now)
    domain.event(s, "portfolio_rebalance", now, "buy", symbol)
    return True


def sell(s, lot, data, now, reason, shares=None):
    symbol = lot_key(s, lot)
    market, raw = split(symbol)
    p = executable(symbol, data, now)
    quote = data["quotes"].get(symbol, {})
    if p is None or quote.get("sourceTime", 0) <= lot["entrySourceTime"]:
        return False
    count = lot["shares"] if shares is None else shares
    if not isinstance(count, int) or not 0 < count <= lot["shares"]:
        return False
    fraction = D(count) / lot["shares"]
    cost = D(lot["entryCost"]) * fraction
    native_price = D(quote["price"])
    rate = p / native_price
    commission = native_price * count * domain.fee(market)
    currency = quote["currency"]
    s["cashBalances"][currency] = str(
        D(s["cashBalances"][currency]) + native_price * count - commission)
    if count == lot["shares"]:
        s["positions"].remove(lot)
    else:
        lot["entryCost"] = str(D(lot["entryCost"]) - cost)
        lot["entryFee"] = str(D(lot["entryFee"]) * (1 - fraction))
        lot["shares"] -= count
    s["fills"].append({
        "id": f"{s['id']}-{len(s['fills']) + 1}", "snapshotId": data["id"],
        "timestamp": now, "market": market, "symbol": raw, "instrumentKey": symbol,
        "currency": currency, "side": "sell", "shares": count, "priceKrw": str(p),
        "nativePrice": str(native_price), "fx": str(rate), "nativeFee": str(commission),
        "gross": str(p * count), "fee": str(commission * rate), "reason": reason,
        "netProfit": str(p * count - commission * rate - cost),
        **{k: lot[k] for k in ("policyVersion", "proposalId", "entryId", "strategyRef",
                              "strategyDigest")},
    })
    if reason in ("position_stop", "sidecar_halt", "ma_exit", "theme_rollover",
                  "strategy_exit", "portfolio_rotation"):
        s.setdefault("portfolioRuntime", {}).setdefault("risk_blocks", {})[symbol] = now + 3600000
    refresh(s, data, now)
    domain.event(s, reason, now, "sell", symbol)
    return True


def assess(s, now):
    data = s.get("latest")
    s["evaluatedAt"] = now
    s["entryBlock"] = domain.block(s, now)
    selected = domain.candidate_symbols(s)
    checks = {}
    for symbol in selected:
        if not data:
            checks[symbol] = "instrument_unverified"
            continue
        native_data, raw = native(data, symbol)
        checks[symbol] = ("market_closed" if not native_data["marketOpen"]
                          else domain.candidate_issue(raw, {**native_data, "fx": data["fx"]}, now))
        item = data["securities"].get(symbol)
        if symbol in domain.standing_symbols(s):
            from app.paper.investment_universe import inverse_issue
            issue = inverse_issue(symbol, item)
            if issue and checks[symbol] != "market_closed":
                checks[symbol] = issue
        if (symbol not in domain.standing_symbols(s) and item
                and item.get("securityType") not in ("STOCK", "FOREIGN_STOCK")):
            checks[symbol] = "general_etf_excluded"
    s["candidateChecks"] = checks
    s["ready"] = sum(v is None for v in checks.values())
    s["total"] = len(selected)
    active_checks = [v for k, v in checks.items()
                     if data and data["markets"][split(k)[0]]["marketOpen"]]
    s["condition"] = (
        "warming_up" if not data else "market_closed" if not data["marketOpen"]
        else "authentication_error" if data["provider"] == "authentication_error"
        else "provider_cooldown" if data["provider"] != "ready"
        else "data_stale" if equity(s, data, now) is None
        else "warming_up" if any(v is not None for v in active_checks) else "ready")
    s["reason"] = s["condition"]
    marks = []
    for lot in s["positions"]:
        symbol = lot_key(s, lot)
        market, _ = split(symbol)
        q = (data or {}).get("quotes", {}).get(symbol) or s.get("valuationQuotes", {}).get(symbol)
        marks.append({"instrumentKey": symbol, "entryId": lot["entryId"], "market": market,
                      "amount": str(mark(s, lot, data, now)) if data
                      and mark(s, lot, data, now) is not None else None,
                      "sourceTime": q.get("sourceTime") if q else None,
                      "ageMs": now - q["sourceTime"] if q else None,
                      "closed": not data or not data["markets"][market]["marketOpen"]})
    s["globalStatus"] = {
        "cashBalances": deepcopy(s["cashBalances"]), "cashKrw": str(cash_value(s, now))
        if cash_value(s, now) is not None else None, "valuationFx": s.get("valuationFx"),
        "markets": {m: {k: v[k] for k in ("marketOpen", "marketClose", "provider")}
                    for m, v in (data or {}).get("markets", {}).items()}, "holdings": marks,
        "equity": str(equity(s, data, now)) if data and equity(s, data, now) is not None else None,
        "marketEntryBlocks": deepcopy(s.get("marketEntryBlocks", {})),
        "executionCosts": "Commissions only; FX reference rate excludes spread/fees/taxes.",
    }


def ingest(s, data, now, runner=None):
    if data["market"] != "GLOBAL" or data["observedAt"] > now or (
            s["latest"] and data["observedAt"] < s["latest"]["observedAt"]):
        return
    s["latest"] = deepcopy(data)
    refresh(s, data, now)
    assess(s, now)
    if s["lifecycle"] == "preparing" and s["condition"] == "ready":
        s["baseline"] = s["cash"]
        s["lifecycle"] = "running"
        domain.event(s, "prepared", now, "command")
    if s["lifecycle"] != "running" or s["lastDecision"] == data["id"]:
        return
    s["lastDecision"] = data["id"]
    s["strategyError"] = None
    marks = [mark(s, lot, data, now) for lot in s["positions"]]
    sidecar = (bool(marks) and all(p is not None for p in marks)
               and sum(marks) <= sum(D(p["entryCost"]) for p in s["positions"]) * D(".95"))
    if sidecar:
        s["sidecarPending"] = True
        s["entriesPaused"] = True
    exited = False
    for lot in s["positions"][:]:
        symbol = lot_key(s, lot)
        native_data, _ = native(data, symbol)
        if not native_data["marketOpen"]:
            continue
        p = executable(symbol, data, now)
        if p is None:
            domain.event(s, "risk_unavailable", now, "risk", symbol)
            continue
        if s.get("sidecarPending"):
            reason = "sidecar_halt"
        elif native_data["closingSoon"] or (
                native_data["marketClose"] - now <= domain.closing_window(native_data["market"])):
            reason = "closing_exit"
        elif s.get("marketEntryBlocks", {}).get(native_data["market"]) == "closing_exit_incomplete":
            reason = "closing_exit"
        elif p * lot["shares"] * (1 - domain.fee(native_data["market"])) <= D(
                lot["entryCost"]) * D(".98"):
            reason = "position_stop"
        else:
            reason = None
        if reason:
            exited = sell(s, lot, data, now, reason) or exited
    if s.get("sidecarPending"):
        s["pending"] = None
        if not s["positions"]:
            s["lifecycle"] = "halted"
            domain.gap(s, "sidecar_halt", now)
        return
    # Legacy allocation modules have no discretionary exits. Their lot provenance is preserved.
    for ref, market in {(p.get("strategyRef", "theme-top3-v1@1"), split(lot_key(s, p))[0])
                        for p in s["positions"]}:
        lots = [p for p in s["positions"] if p.get("strategyRef") == ref
                and split(lot_key(s, p))[0] == market]
        context = domain.strategy_context(s, data, now, domain.candidate_groups(s), lots, False)
        context["active_market"] = market
        signal = domain.run_strategy(s, ref, lots[0].get("strategyDigest"), context, now, runner)
        if signal:
            for lot in lots:
                if lot["symbol"] in signal["exits"]:
                    exited = sell(s, lot, data, now, signal["exits"][lot["symbol"]]) or exited
    if (exited or s.get("strategyError") or s["entryBlock"] != "none"
            or s["condition"] != "ready" or (s.get("policy") or {}).get("schema_version") != 8):
        s["pending"] = None
        return
    from app.paper.portfolio import rebalance
    rebalance(s, data, now, runner)
