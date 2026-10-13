"""Decimal money helpers. Floats never touch a balance."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .config import CURRENCY_ALIASES, MID_PER_USD, SUPPORTED_CURRENCIES

CENT = Decimal("0.01")
RATE_Q = Decimal("0.000001")


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc


def q(value) -> Decimal:
    """Round to cents."""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def norm_ccy(code: str) -> str:
    if code is None:
        raise ValueError("currency missing")
    c = CURRENCY_ALIASES.get(str(code).strip().upper())
    if c is None or c not in SUPPORTED_CURRENCIES:
        raise ValueError(f"unsupported currency: {code!r}")
    return c


def mid_rate(src: str, dst: str) -> Decimal:
    """Units of dst per 1 unit of src."""
    return MID_PER_USD[norm_ccy(dst)] / MID_PER_USD[norm_ccy(src)]


def convert_mid(amount, src: str, dst: str) -> Decimal:
    return D(amount) * mid_rate(src, dst)


def to_usd(amount, ccy: str) -> Decimal:
    return D(amount) / MID_PER_USD[norm_ccy(ccy)]


def fmt(amount, ccy: str) -> str:
    return f"{ccy} {q(amount):,.2f}"
