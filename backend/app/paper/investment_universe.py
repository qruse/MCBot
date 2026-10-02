"""Inspected daily -1x index products; external text is never executable admission code."""

from decimal import Decimal, InvalidOperation

from app.paper.contracts import STANDING_INVERSE

INDEX_INVERSES = {
    f"{market}:{symbol}": {"name": name, "source_url": url}
    for market, products in STANDING_INVERSE.items()
    for symbol, name, url in products
}


def inverse_key(item):
    return f'{item.market}:{item.symbol}'


def inverse_groups(groups):
    return [
        {
            **group.model_dump(mode="json"),
            "candidates": [
                {**item.model_dump(mode="json"),
                 "source_urls": [INDEX_INVERSES[inverse_key(item)]["source_url"]]}
                for item in group.candidates
            ],
        }
        for group in groups
    ]


def inverse_issue(key, security):
    if key not in INDEX_INVERSES:
        return "index_inverse_not_admitted"
    if not security:
        return "instrument_unverified"
    try:
        factor = Decimal(str(security.get("leverageFactor")))
    except (InvalidOperation, ValueError):
        return "index_inverse_unverified"
    if security.get("securityType") not in ("ETF", "FOREIGN_ETF") or factor != -1:
        return "index_inverse_ineligible"
    return None
