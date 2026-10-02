"""One server collector reuses Toss's global pacing/cache; no calls before Start."""

import hashlib
import json
import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app import toss
from app.paper.contracts import STANDING_INVERSE, symbols
from app.paper.domain import closing_window, instrument_issue, positive


def timestamp(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(date.timestamp() * 1000) if date.tzinfo else 0
    except (ValueError, TypeError, AttributeError):
        return 0


def period(day, market):
    return (
        (day.get("integrated") or {}).get("regularMarket")
        if market == "KR"
        else day.get("regularMarket")
    )


def calendar_state(calendar, market, now):
    days = list((calendar or {}).get("data", {}).values())
    hours = [(d, period(d, market)) for d in days if isinstance(d, dict)]
    hours = [(d, p) for d, p in hours if p]
    current = next(
        (p for _, p in hours if timestamp(p["startTime"]) <= now < timestamp(p["endTime"])), None
    )
    completed = sorted(
        (
            (timestamp(p["endTime"]), d["date"])
            for d, p in hours
            if 0 < timestamp(p["endTime"]) <= now
        ),
        reverse=True,
    )
    close = timestamp(current["endTime"]) if current else 0
    return {
        "marketOpen": bool(current),
        "marketClose": close,
        "closingSoon": bool(current) and close - now <= closing_window(market),
        "expectedDailyClose": completed[0][0] if completed else 0,
        "completedDate": completed[0][1] if completed else "",
    }


class GlobalCollector:
    def __init__(self):
        self.collectors = {market: Collector(market) for market in ("KR", "US")}
        self.fx = None
        self.fx_updated = 0
        self.fx_retry_at = 0

    async def collect(self, held, candidates=(), reference=()):
        from app.paper.global_account import split
        for market, collector in self.collectors.items():
            def members(items, native_market=market):
                return [split(s)[1] for s in items if split(s)[0] == native_market]
            await collector.collect(members(held), members(candidates), members(reference))
        now = int(time.time() * 1000)
        if (now >= self.fx_retry_at and any(calendar_state(c.calendar, m, now)["marketOpen"]
                for m, c in self.collectors.items()) and now - self.fx_updated >= 300000):
            try:
                self.fx = await toss.global_fx()
                self.fx_updated = int(time.time() * 1000)
                self.fx_retry_at = 0
            except Exception:
                # Preserve actual FX source times. An error cannot manufacture fresh currency.
                wait = toss.status().get("retry_after_seconds") or 60
                self.fx_retry_at = int(time.time() * 1000) + max(1, wait) * 1000

    def snapshot(self, now):
        from app.paper.global_account import combine
        markets = {m: c.snapshot(now) for m, c in self.collectors.items()}
        fx = max((v for v in (markets["US"].get("fx"), self.fx) if v),
                 key=lambda v: (v["validFrom"], v["receivedAt"]), default=None)
        return combine(markets, now, fx)


class Collector:
    def __init__(self, market):
        self.market = market
        self.calendar = None
        self.prices = None
        self.histories = {}
        self.history_attempts = {}
        self.securities = {}
        self.quote_scope = ()
        self.updated = {}
        self.retry_at = 0
        self.provider = "ready"

    async def collect(self, held, candidates=(), reference=None):
        now = int(time.time() * 1000)
        if self.provider == "authentication_error" or now < self.retry_at:
            return
        state = calendar_state(self.calendar, self.market, now)
        reference = symbols(self.market) if reference is None else reference
        ordered = list(dict.fromkeys([*held, *candidates, *reference]))
        self.histories = {key: value for key, value in self.histories.items() if key in ordered}
        self.history_attempts = {
            key: value for key, value in self.history_attempts.items() if key in ordered
        }
        self.securities = {key: value for key, value in self.securities.items() if key in ordered}
        metadata_due = any(now - self.updated.get(f"stock:{s}", 0) >= 300000 for s in ordered)
        eligible = [
            s
            for s in ordered
            if not instrument_issue(s, {"market": self.market, "securities": self.securities}, now)
        ]
        quote_symbols = list(dict.fromkeys([*held, *eligible]))
        quote_interval = (
            toss.CLOSING_QUOTE_POLL_SECONDS if state.get("closingSoon")
            else toss.QUOTE_POLL_SECONDS if held else toss.FLAT_QUOTE_POLL_SECONDS
        )
        quotes_due = (
            now - self.updated.get("prices", 0) >= quote_interval * 1000
            or tuple(quote_symbols) != self.quote_scope
        )
        try:
            if now - self.updated.get("calendar", 0) >= 3600000:
                self.calendar = await toss.calendar(self.market)
                self.updated["calendar"] = int(time.time() * 1000)
            elif state["marketOpen"] and held and quotes_due:
                # Refresh protected holdings before a newly proposed symbol can fail validation.
                self.prices = await toss.prices(",".join(quote_symbols))
                self.quote_scope = tuple(quote_symbols)
                self.updated["prices"] = int(time.time() * 1000)
            elif state["marketOpen"] and metadata_due:
                response = await toss.stocks(ordered)
                received = timestamp(response["synced_at"])
                by_symbol = {item["symbol"]: item for item in response["data"]}
                for symbol in ordered:
                    self.securities[symbol] = {
                        **by_symbol.get(symbol, {"symbol": symbol, "status": "UNKNOWN"}),
                        "receivedAt": received,
                    }
                    self.updated[f"stock:{symbol}"] = int(time.time() * 1000)
            elif state["marketOpen"] and quote_symbols and quotes_due:
                self.prices = await toss.prices(",".join(quote_symbols))
                self.quote_scope = tuple(quote_symbols)
                self.updated["prices"] = int(time.time() * 1000)
            elif state["marketOpen"]:
                due = [s for s in eligible if now - self.updated.get(s, 0) >= 900000]
                if due:
                    # A failed symbol must not monopolize every recovery attempt.
                    symbol = min(due, key=lambda s: self.history_attempts.get(s, 0))
                    self.history_attempts[symbol] = now
                    self.histories[symbol] = await toss.strategy(symbol)
                    self.updated[symbol] = int(time.time() * 1000)
            status = toss.status()
            self.provider = status["state"]
            if self.provider == "cooldown":
                self.retry_at = int(time.time() * 1000) + max(
                    1, status["retry_after_seconds"] or 60
                ) * 1000
        except Exception:
            # Do not export response bodies or credentials. The adapter persists its cooldown.
            status = toss.status()
            self.provider = (
                "authentication_error" if status["state"] == "authentication_error" else "cooldown"
            )
            wait = status["retry_after_seconds"] if status["state"] == "cooldown" else 60
            self.retry_at = int(time.time() * 1000) + max(1, wait or 60) * 1000

    def snapshot(self, now):
        state = calendar_state(self.calendar, self.market, now)
        data = {
            "market": self.market,
            "observedAt": now,
            "quotes": {},
            "displayQuotes": {},
            "minute": {},
            "daily": {},
            "fx": None,
            "provider": self.provider,
            "securities": self.securities.copy(),
            **state,
        }
        zone = ZoneInfo("Asia/Seoul" if self.market == "KR" else "America/New_York")
        previous_prices = {}
        for symbol, response in self.histories.items():
            for interval in ("minute", "daily"):
                bars = []
                quality = response["quality"][interval]
                for bar in response[interval] if quality["valid_values"] else []:
                    start = timestamp(bar.get("timestamp"))
                    if not start:
                        continue
                    date = datetime.fromtimestamp(start / 1000, zone).date().isoformat()
                    if interval == "daily" and date == state["completedDate"]:
                        close = state["expectedDailyClose"]
                        previous_prices[symbol] = positive(bar.get("closePrice"))
                    else:
                        close = start + (60000 if interval == "minute" else 86400000)
                    if close <= now and (interval == "minute" or date <= state["completedDate"]):
                        bars.append(
                            {"close": bar.get("closePrice"), "closedAt": close, "complete": True}
                        )
                data[interval][symbol] = {
                    "candles": sorted(bars, key=lambda b: b["closedAt"]),
                    "receivedAt": timestamp(quality["received_at"]),
                }
        for quote in (self.prices or {}).get("data", []):
            symbol = quote["symbol"]
            quality = self.prices["quality"][symbol]
            p = positive(quote.get("lastPrice")) if quality["valid"] else None
            prior = previous_prices.get(symbol)
            data["quotes"][symbol] = {
                "price": str(p) if p else None,
                "currency": quote.get("currency"),
                "sourceTime": timestamp(quote.get("timestamp")),
                "receivedAt": timestamp(quality.get("received_at")),
                "changePercent": str((p / prior - 1) * 100) if p and prior else None,
            }
            # Dated display marks are separate from executable quotes. Never renew source time.
            display_price = positive(quote.get("lastPrice"))
            source_time = timestamp(quote.get("timestamp"))
            if (
                display_price
                and quote.get("currency") == ("KRW" if self.market == "KR" else "USD")
                and 0 < source_time <= now
                and now - source_time <= 7 * 86400000
            ):
                data["displayQuotes"][symbol] = {
                    **data["quotes"][symbol], "price": str(display_price),
                }
        fx = (self.prices or {}).get("fx_quality")
        if fx and fx["valid"]:
            data["fx"] = {
                "rate": self.prices["usd_krw"],
                "validFrom": timestamp(fx["source_at"]),
                "validUntil": timestamp(fx["valid_until"]),
                "receivedAt": timestamp(fx["received_at"]),
            }
        identity = {k: v for k, v in data.items() if k != "observedAt"}
        data["id"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return data


def demo_snapshot(market, now):
    """Explicit synthetic inputs. This function is never a failed-provider fallback."""
    tick = now // 30000
    observed = tick * 30000
    daily_close = now // 86400000 * 86400000 - 86400000
    data = {
        "id": f"demo-{market}-{tick}",
        "market": market,
        "observedAt": observed,
        "quotes": {},
        "minute": {},
        "daily": {},
        "fx": {
            "rate": "1380",
            "validFrom": observed,
            "validUntil": observed + 300000,
            "receivedAt": observed,
        },
        "expectedDailyClose": daily_close,
        "marketOpen": True,
        "marketClose": now // 86400000 * 86400000 + 86400000,
        "closingSoon": False,
        "provider": "ready",
    }
    fixture_symbols = list(
        dict.fromkeys([*symbols(market), *[s[0] for s in STANDING_INVERSE[market]]])
    )
    for index, symbol in enumerate(fixture_symbols):
        data.setdefault("securities", {})[symbol] = {
            "symbol": symbol,
            "name": symbol,
            "market": "KOSPI" if market == "KR" else "NASDAQ",
            "currency": "KRW" if market == "KR" else "USD",
            "status": "ACTIVE",
            "securityType": "STOCK" if index < 3 else "ETF",
            "leverageFactor": "-1" if symbol in {s[0] for s in STANDING_INVERSE[market]}
            else None,
            "receivedAt": observed,
            "koreanMarketDetail": {"liquidationTrading": False, "krxTradingSuspended": False},
        }
        base = Decimal(
            [72000, 185000, 115000, 4200, 2300, 4100, 4300][index]
            if market == "KR"
            else [145, 220, 155, 40, 35, 28, 45][index]
        )
        slope = Decimal(".003") if index < 3 else Decimal("-.001")
        data["quotes"][symbol] = {
            "price": str(base * (1 + Decimal(tick % 10) / 10000)),
            "currency": "KRW" if market == "KR" else "USD",
            "sourceTime": observed,
            "receivedAt": observed,
            "changePercent": "1.5" if index < 3 else "-1",
        }
        for interval, count, step, end in (
            ("minute", 40, 60000, observed - 60000),
            ("daily", 100, 86400000, daily_close),
        ):
            data[interval][symbol] = {
                "receivedAt": observed,
                "candles": [
                    {
                        "close": str(base * (1 + (i - count + 1) * slope)),
                        "closedAt": end - (count - 1 - i) * step,
                        "complete": True,
                    }
                    for i in range(count)
                ],
            }
    return data
