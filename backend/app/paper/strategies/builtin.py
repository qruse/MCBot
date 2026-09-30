"""Frozen theme strategy v1. Pure standard-library code, also runnable by the worker."""

from decimal import Decimal as D


def trend(bars, fast=8, slow=26, offset=4):
    values = [D(str(b["close"])) for b in bars]
    a = sum(values[-fast:]) / fast
    b = sum(values[-fast - offset : -offset]) / fast
    c = sum(values[-slow:]) / slow
    return a, b, c, (a - c) / c * 100 + (a - b) / b * 200


def long_score(symbol, data):
    bars = data["daily"][symbol]["candles"]
    return trend(bars, 20, 60, 8)[3] * D(".45") + trend(bars, 20, 80, 10)[3] * D(".55")


def score(symbol, data):
    a, b, c, value = trend(data["minute"][symbol]["candles"])
    return (
        value * (1 if a > b and a > c else D(".35"))
        + long_score(symbol, data) * D(".65")
        + D(str(data["quotes"][symbol]["changePercent"])) * D(".15")
    )


def winner(data, groups):
    ranked = []
    for name, group in groups.items():
        momentum = sum(score(s, data) for s in group) / len(group)
        rising = 0
        for symbol in group[:3]:
            a, b, c, _ = trend(data["minute"][symbol]["candles"])
            rising += a > b and a > c and long_score(symbol, data) > 0
        if momentum > D(".12") and rising >= 2:
            ranked.append((momentum, name))
    return max(ranked, default=(0, None))[1]


def decide(context):
    data = context["data"]
    exits = {}
    for position in context["positions"]:
        symbol = position["symbol"]
        if symbol in context["minute_ready"]:
            a, b, c, value = trend(data["minute"][symbol]["candles"])
            if a < c * D(".998") or a < b * D(".99875") and value < 0:
                exits[symbol] = "ma_exit"
    group = context["active_symbols"]
    if group and set(group) <= set(context["candidate_ready"]):
        falling = 0
        for symbol in group:
            a, b, c, value = trend(data["minute"][symbol]["candles"])
            falling += a < c * D(".996") and a < b * D(".9975") and value < D("-.18")
        if sum(score(s, data) for s in group) < 0 and falling >= 3:
            for position in context["positions"]:
                exits.setdefault(position["symbol"], "theme_rollover")
    return {
        "entry_group": winner(data, context["groups"]) if context["can_enter"] else None,
        "exits": exits,
        "weights": {},
        "rotate": True,
        "reason": "Frozen theme trend rules.",
    }
