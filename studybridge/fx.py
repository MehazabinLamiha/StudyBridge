"""Currency quotes for in-wallet conversion."""
from decimal import Decimal

from .config import RATE_SOURCE, WALLET_FX_SPREAD
from .money import D, RATE_Q, mid_rate, norm_ccy, q


def quote(amount, src: str, dst: str, spread: Decimal = WALLET_FX_SPREAD) -> dict:
    src, dst = norm_ccy(src), norm_ccy(dst)
    amount = D(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    mid = mid_rate(src, dst)
    applied = mid if src == dst else mid * (1 - spread)
    return {
        "from": src,
        "to": dst,
        "amount": q(amount),
        "mid_rate": mid.quantize(RATE_Q),
        "applied_rate": applied.quantize(RATE_Q),
        "spread_pct": q(spread * 100) if src != dst else q(0),
        "you_get": q(amount * applied),
        "rate_source": RATE_SOURCE,
    }
